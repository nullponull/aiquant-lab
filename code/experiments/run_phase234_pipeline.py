"""Phase 2-3 統合パイプライン (実データ)

GitHub Actions (週次 cron) またはローカルで実行する。
この環境ではネットワークの都合で Yahoo Finance に接続できない場合が
あるため、実行は CI / ローカルを想定。

実行内容:
  Phase 2: SPY 10 年で 10 戦略を walk-forward 評価 (5 フォールド, purge=5)
  Phase 3a: ボラティリティ予測の評価 (EWMA / HAR-RV vs 定数, QLIKE)
  Phase 3b: レジーム検出 (2 状態 HMM) と持続性
  Phase 3c: 40 銘柄ユニバースで 12-1 モメンタム / 短期リバーサルの Rank IC

出力: results/phaseN/report_<date>.md (自動解釈つき)

実行:
    uv run python code/experiments/run_phase234_pipeline.py
    uv run python code/experiments/run_phase234_pipeline.py --skip-universe
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code"))

import pandas as pd  # noqa: E402

from strategies.base import backtest, fetch_spy_data  # noqa: E402
from strategies.strategies import STRATEGIES  # noqa: E402
from validation.walkforward import run_walkforward, aggregate_walkforward  # noqa: E402
from forecast.volatility import evaluate_vol_forecasts  # noqa: E402
from forecast.regime import fit_regime_hmm, regime_persistence  # noqa: E402
from crosssect.ranking import (  # noqa: E402
    SIGNALS, evaluate_signal, fetch_universe)
from stats.significance import deflated_sharpe_ratio  # noqa: E402


def fetch_spy_long(years: int = 10) -> pd.DataFrame:
    return fetch_spy_data(period_days=int(years * 365.25))


def phase2_walkforward(df: pd.DataFrame, lines: list[str]) -> None:
    lines.append("## Phase 2: Walk-forward 評価 (10 戦略)")
    lines.append("")
    fns = {name: fn for name, fn in STRATEGIES.items()}
    table = run_walkforward(df, fns, backtest, n_folds=5,
                            min_train=504, purge=5)
    agg = aggregate_walkforward(table)
    lines.append(f"- 期間: {df.index[0].date()} 〜 {df.index[-1].date()} "
                 f"({len(df)} 営業日, 5 フォールド, purge=5)")
    lines.append("")
    lines.append("| 戦略 | 平均Sharpe | フォールド勝率 | 平均リターン | 最悪DD |")
    lines.append("|---|---|---|---|---|")
    for name, row in agg.iterrows():
        lines.append(f"| {name} | {row['mean_sharpe']:+.2f} | "
                     f"{row['pct_positive_folds']*100:.0f}% | "
                     f"{row['mean_return']*100:+.2f}% | "
                     f"{row['worst_drawdown']*100:.1f}% |")
    lines.append("")

    # 最良戦略を DSR で多重検定補正 (フォールド平均ではなく全期間日次で)
    best = agg.index[0]
    from strategies.base import equity_curve
    sharpes = []
    rets_map = {}
    for name, fn in fns.items():
        eq = equity_curve(df, fn(df))
        r = eq.pct_change().dropna()
        rets_map[name] = r
        sd = r.std(ddof=1)
        sharpes.append(float(r.mean() / sd) if sd > 0 else 0.0)
    dsr = deflated_sharpe_ratio(rets_map[best], n_trials=len(fns),
                                all_trial_sharpes=sharpes)
    lines.append(f"- 最良戦略 **{best}** の DSR: **{dsr['dsr']:.3f}** "
                 f"({'5%有意' if dsr['significant_5pct'] else '非有意 — 10 戦略から選んだ偶然の範囲'})")
    lines.append("")


def phase3a_volatility(df: pd.DataFrame, lines: list[str]) -> None:
    lines.append("## Phase 3a: ボラティリティ予測 (QLIKE, 小さいほど良い)")
    lines.append("")
    ret = df["close"].pct_change()
    res = evaluate_vol_forecasts(ret, min_train=252)
    lines.append("| モデル | QLIKE | 対定数改善率 |")
    lines.append("|---|---|---|")
    for name, row in res.iterrows():
        lines.append(f"| {name} | {row['qlike']:.4f} | "
                     f"{row['qlike_improvement_vs_const']*100:+.1f}% |")
    lines.append("")
    best_imp = res["qlike_improvement_vs_const"].max()
    if best_imp > 0.05:
        lines.append(f"→ **分散には予測可能性がある** (定数比 {best_imp*100:.0f}% 改善)。"
                     "方向ではなく変動の大きさが、このプロジェクトの『予測可能な形』の足場。")
    else:
        lines.append("→ この期間ではボラ予測の改善が小さい。期間・銘柄を変えて要再検証。")
    lines.append("")


def phase3b_regime(df: pd.DataFrame, lines: list[str]) -> None:
    lines.append("## Phase 3b: レジーム検出 (2 状態 HMM)")
    lines.append("")
    ret = df["close"].pct_change().dropna()
    hmm = fit_regime_hmm(ret)
    p = regime_persistence(hmm)
    cur = hmm.filtered_prob.iloc[-1]
    lines.append(f"- 静穏レジーム: 日次σ={hmm.stds[0]*100:.2f}% / "
                 f"荒れレジーム: 日次σ={hmm.stds[1]*100:.2f}% "
                 f"(比 {p['vol_ratio_turbulent_to_calm']:.1f}x)")
    lines.append(f"- 持続性: P(静穏→静穏)={p['p_stay_calm']:.3f} "
                 f"(期待継続 {p['expected_calm_duration_days']:.0f} 日), "
                 f"P(荒れ→荒れ)={p['p_stay_turbulent']:.3f} "
                 f"(期待継続 {p['expected_turbulent_duration_days']:.0f} 日)")
    lines.append(f"- 現在 ({hmm.filtered_prob.index[-1].date()}): "
                 f"静穏確率 {cur['calm']*100:.0f}%")
    lines.append("")
    lines.append("→ 対角遷移確率が高い = 「明日のレジーム」は予測できる。"
                 "これが条件付き運用 (荒れたら縮小) の根拠になる。")
    lines.append("")


def phase3c_cross_section(lines: list[str]) -> None:
    lines.append("## Phase 3c: クロスセクショナル Rank IC (40 銘柄, 5 年)")
    lines.append("")
    lines.append("> 注意: 現時点の構成銘柄を遡って使うため生存バイアスあり。"
                 "point-in-time ユニバース化が今後の課題。")
    lines.append("")
    prices = fetch_universe()
    lines.append("| シグナル | 平均IC | NW t値 | 5%有意 | 正IC率 |")
    lines.append("|---|---|---|---|---|")
    for name, fn in SIGNALS.items():
        r = evaluate_signal(prices, fn, horizon=21)
        mark = "✅" if r["significant_5pct"] else "—"
        lines.append(f"| {name} | {r['mean_ic']:+.3f} | {r['t_stat_nw']:+.2f} | "
                     f"{mark} | {r['pct_positive']*100:.0f}% |")
    lines.append("")


def phase3d_distribution(df: pd.DataFrame, lines: list[str]) -> None:
    from forecast.distribution import evaluate_calibration
    lines.append("## Phase 3d: 分布予測の較正 — 「予測可能な形」の判定")
    lines.append("")
    ret = df["close"].pct_change()
    res = evaluate_calibration(ret, min_train=252)
    m, b = res["model"], res["baseline_const_gaussian"]
    lines.append("| 指標 | t+EWMA 分布予測 | 定数分散ガウシアン |")
    lines.append("|---|---|---|")
    lines.append(f"| PIT KS p値 (>0.05で較正合格) | **{m['ks_pvalue']:.3f}** | {b['ks_pvalue']:.3f} |")
    lines.append(f"| 95%区間カバレッジ (名目0.95) | {m['coverage']['95%']:.3f} | {b['coverage']['95%']:.3f} |")
    lines.append(f"| 99%区間カバレッジ (名目0.99) | {m['coverage']['99%']:.3f} | {b['coverage']['99%']:.3f} |")
    lines.append(f"| 平均対数スコア (高いほど良い) | {m['mean_log_score']:.3f} | {b['mean_log_score']:.3f} |")
    lines.append("")
    lines.append(f"- 方向確率の Brier: {res['direction_brier']:.4f} "
                 f"(コイン投げ {res['direction_brier_coin']:.4f}) → "
                 f"{'方向に予測力あり' if res['direction_predictable'] else '方向は予測できない (想定通り)'}")
    lines.append(f"- 推定自由度 ν={m['fitted_df_last']:.1f} (小さいほどファットテール)")
    lines.append("")
    if m["calibrated_5pct"]:
        lines.append("→ **判定: 分布の意味で予測可能。** 明日のリターンの確率分布"
                     " (幅と尾) は検定に合格する精度で予測できている。"
                     "一方で方向 (平均) は予測できない。これがこのプロジェクトの"
                     "言う「予測可能な形」の現在地。")
    else:
        lines.append("→ 判定: この期間では較正不合格。モデル改善 (レジーム条件付き"
                     "スケール等) が必要。")
    lines.append("")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-universe", action="store_true")
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args()

    lines = [f"# Phase 2-3 パイプラインレポート ({date.today().isoformat()})", ""]
    lines.append("自動生成: `code/experiments/run_phase234_pipeline.py`")
    lines.append("")

    df = fetch_spy_long(args.years)
    phase2_walkforward(df, lines)
    phase3a_volatility(df, lines)
    phase3b_regime(df, lines)
    phase3d_distribution(df, lines)
    if not args.skip_universe:
        try:
            phase3c_cross_section(lines)
        except Exception as e:  # ユニバース取得失敗時もレポートは出す
            lines.append(f"## Phase 3c: スキップ (取得失敗: {e})")
            lines.append("")

    out_dir = REPO_ROOT / "results" / "phase23"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"report_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n保存: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
