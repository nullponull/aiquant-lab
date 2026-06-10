"""ペーパートレーディング日次実行 (Phase 4)

方針 (v1): レジーム条件付き・ボラターゲティングの SPY エクスポージャー
    weight(SPY) = P(静穏レジーム) × min(1, 目標ボラ / 予測ボラ)

これは「方向予測」を一切使わない。使うのは検証済みの予測可能性
(レジーム持続性とボラ予測) のみ。これがこのプロジェクトの主張する
「予測可能な形」の最小実装であり、ペーパー運用でその主張を
未来のデータに晒す。

GitHub Actions の日次 cron から実行し、状態 (results/paper/state.json)
をコミットする。実発注は行わない。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "code"))

from strategies.base import fetch_spy_data  # noqa: E402
from forecast.volatility import ewma_variance  # noqa: E402
from forecast.regime import fit_regime_hmm  # noqa: E402
from paper.paper_trader import PaperState, rebalance, performance_summary  # noqa: E402

STATE_PATH = REPO_ROOT / "results" / "paper" / "state.json"
TARGET_ANNUAL_VOL = 0.10  # 目標年率ボラ 10%


def compute_target_weight(df) -> dict:
    ret = df["close"].pct_change().dropna()
    # レジーム (filtered = その時点までの情報のみ)
    hmm = fit_regime_hmm(ret)
    p_calm = float(hmm.filtered_prob["calm"].iloc[-1])
    # ボラ予測 (EWMA, 1-step-ahead)
    h = float(ewma_variance(ret).iloc[-1])
    forecast_annual_vol = np.sqrt(h * 252)
    vol_scale = min(1.0, TARGET_ANNUAL_VOL / max(forecast_annual_vol, 1e-6))
    w = p_calm * vol_scale
    return {
        "weight": float(np.clip(w, 0.0, 1.0)),
        "p_calm": p_calm,
        "forecast_annual_vol": float(forecast_annual_vol),
        "vol_scale": float(vol_scale),
    }


def main() -> int:
    df = fetch_spy_data(period_days=900)  # HMM 学習に約 2.5 年
    info = compute_target_weight(df)

    today_open = float(df["open"].iloc[-1])
    as_of = str(df.index[-1].date())

    if STATE_PATH.exists():
        state = PaperState.load(STATE_PATH)
    else:
        state = PaperState.new(1_000_000.0)

    state = rebalance(state,
                      target_weights={"SPY": info["weight"]},
                      prices={"SPY": today_open},
                      as_of=as_of,
                      max_weight=1.0,        # 単一 ETF 方針のため
                      max_drawdown=-0.20)
    state.save(STATE_PATH)

    summary = performance_summary(state)
    print(f"as_of={as_of} open={today_open:.2f}")
    print(f"P(calm)={info['p_calm']:.2f} "
          f"forecast_vol={info['forecast_annual_vol']*100:.1f}% "
          f"→ weight(SPY)={info['weight']:.2f}")
    print(f"equity=¥{summary['current_equity']:,.0f} "
          f"({summary['total_return']*100:+.2f}%, "
          f"MaxDD {summary['max_drawdown']*100:.1f}%)")
    if state.frozen:
        print(f"⚠️ KILL SWITCH 作動済み: {state.kill_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
