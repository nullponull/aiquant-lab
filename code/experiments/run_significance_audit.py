"""有意性監査: 既存の実験結果に統計検定をかける

「勝った/負けた」を「偶然と区別できるか」に変換するスクリプト。

対象:
1. results/004/equity_curves.csv (Ep7: 10 戦略 30 日)
   - 各戦略の Deflated Sharpe Ratio (10 戦略試した多重検定を補正)
   - White's Reality Check (最良戦略 vs Buy-and-Hold)
2. 方向精度の二項検定 (Ep2/Ep6 の数値を引数で指定可能)

実行:
    uv run python code/experiments/run_significance_audit.py
    uv run python code/experiments/run_significance_audit.py --hits 19 --total 30

出力:
    results/significance_audit/audit_<date>.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stats.significance import (  # noqa: E402
    binomial_directional_test,
    deflated_sharpe_ratio,
    whites_reality_check,
)


def audit_equity_curves(path: Path, benchmark_col: str = "Buy-and-Hold") -> list[str]:
    lines: list[str] = []
    eq = pd.read_csv(path, index_col=0, parse_dates=True)
    rets = eq.pct_change().dropna(how="all").fillna(0)
    n_obs = len(rets)
    lines.append(f"## エクイティカーブ監査: `{path.relative_to(REPO_ROOT)}`")
    lines.append("")
    lines.append(f"- 観測数: {n_obs} 営業日 / 戦略数: {rets.shape[1]}")
    if n_obs < 60:
        lines.append(f"- ⚠️ **観測数 {n_obs} は検定するには少なすぎます。"
                     "以下の結果は『この期間では何も言えない』ことの確認です。**")
    lines.append("")

    # --- DSR ---
    lines.append("### Deflated Sharpe Ratio (多重検定補正)")
    lines.append("")
    lines.append("| 戦略 | SR(日次) | DSR | 5%有意 |")
    lines.append("|---|---|---|---|")
    sharpes = {}
    for col in rets.columns:
        r = rets[col].to_numpy()
        sd = r.std(ddof=1)
        sharpes[col] = float(r.mean() / sd) if sd > 0 else 0.0
    trial_srs = list(sharpes.values())
    n_trials = len(trial_srs)
    for col in rets.columns:
        try:
            res = deflated_sharpe_ratio(rets[col], n_trials=n_trials,
                                        all_trial_sharpes=trial_srs)
            mark = "✅" if res["significant_5pct"] else "—"
            lines.append(f"| {col} | {sharpes[col]:+.4f} | {res['dsr']:.3f} | {mark} |")
        except ValueError as e:
            lines.append(f"| {col} | {sharpes[col]:+.4f} | 計算不可 ({e}) | — |")
    lines.append("")

    # --- Reality Check ---
    if benchmark_col in rets.columns and rets.shape[1] >= 3 and n_obs >= 20:
        bench = rets[benchmark_col]
        strats = rets.drop(columns=[benchmark_col])
        rc = whites_reality_check(strats, bench, n_boot=2000)
        lines.append(f"### White's Reality Check (vs {benchmark_col})")
        lines.append("")
        lines.append(f"- 最良戦略: **{rc['best_strategy']}** "
                     f"(平均日次超過 {rc['best_mean_daily_excess']*100:+.3f}%)")
        lines.append(f"- p 値: **{rc['p_value']:.3f}** "
                     f"({'5%有意 — データスヌーピングでは説明しにくい' if rc['significant_5pct'] else '有意でない — 最良戦略の優位は偶然と区別できない'})")
        lines.append("")
    return lines


def audit_directional(hits: int, total: int) -> list[str]:
    res = binomial_directional_test(hits, total)
    lines = ["## 方向精度の二項検定", ""]
    lines.append(f"- 精度: {res['accuracy']*100:.1f}% ({hits}/{total})")
    lines.append(f"- 95% 信頼区間 (Wilson): "
                 f"[{res['ci_low']*100:.1f}%, {res['ci_high']*100:.1f}%]")
    lines.append(f"- p 値 (vs 50%): **{res['p_value']:.3f}** "
                 f"({'5%有意' if res['significant_5pct'] else '有意でない — コイン投げと区別できない'})")
    lines.append("")
    lines.append("> 注意: 予測ホライズンが重複したイベント系列ではこの検定は楽観側に歪みます。")
    lines.append("")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--equity-csv", default=str(REPO_ROOT / "results/004/equity_curves.csv"))
    ap.add_argument("--hits", type=int, default=19,
                    help="方向予測の正解数 (デフォルトは Ep2 相当の例)")
    ap.add_argument("--total", type=int, default=30)
    args = ap.parse_args()

    out_lines = [f"# 有意性監査レポート ({date.today().isoformat()})", ""]
    out_lines.append("自動生成: `code/experiments/run_significance_audit.py`")
    out_lines.append("")

    eq_path = Path(args.equity_csv)
    if eq_path.exists():
        out_lines += audit_equity_curves(eq_path)
    else:
        out_lines.append(f"(equity curve ファイルが見つかりません: {eq_path})")
        out_lines.append("")

    out_lines += audit_directional(args.hits, args.total)

    out_dir = REPO_ROOT / "results" / "significance_audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"audit_{date.today().isoformat()}.md"
    out_path.write_text("\n".join(out_lines), encoding="utf-8")

    print("\n".join(out_lines))
    print(f"\n保存: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
