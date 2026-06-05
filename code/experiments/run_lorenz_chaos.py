"""Ep12: Lorenz 系で「初期値 0.001% 差がリターン軌跡を真逆にする」を実証

設計:
  - Lorenz attractor (σ=10, ρ=28, β=8/3) を 2 つの初期値で並列シミュレート
  - 初期値差: 0.001% (1e-5 相対)
  - Lorenz x 座標を「日次リターン」として扱い、複利で 252 日の equity を計算
  - 2 系列の最終リターンと相関を比較

出力:
  results/012/lorenz_trajectories.csv
  results/012/summary.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]


def lorenz_rhs(state, sigma=10.0, rho=28.0, beta=8.0/3.0):
    x, y, z = state
    return np.array([
        sigma * (y - x),
        x * (rho - z) - y,
        x * y - beta * z,
    ])


def rk4_step(state, dt, **params):
    k1 = lorenz_rhs(state, **params)
    k2 = lorenz_rhs(state + dt * k1 / 2, **params)
    k3 = lorenz_rhs(state + dt * k2 / 2, **params)
    k4 = lorenz_rhs(state + dt * k3, **params)
    return state + dt * (k1 + 2*k2 + 2*k3 + k4) / 6


def simulate(initial: np.ndarray, n_steps: int, dt: float = 0.01):
    states = np.zeros((n_steps, 3))
    s = initial.copy()
    for i in range(n_steps):
        states[i] = s
        s = rk4_step(s, dt)
    return states


def main() -> int:
    print('=== Ep12: Lorenz カオスシミュレーション ===')
    print()
    # 初期値: 標準 vs 0.001% (1e-5 相対) 差
    init_a = np.array([1.0, 1.0, 1.0])
    perturb_pct = 1e-5  # 0.001%
    init_b = init_a * (1.0 + perturb_pct)
    print(f'初期値 A: {init_a}')
    print(f'初期値 B: {init_b} (diff: {perturb_pct*100}%)')
    print()

    # 252 日 (1 年) ぶん、それぞれ 100 micro-step で総 25,200 step
    n_steps = 252 * 100
    dt = 0.01

    print(f'シミュレーション {n_steps} ステップ (dt={dt}) ...', flush=True)
    traj_a = simulate(init_a, n_steps, dt)
    traj_b = simulate(init_b, n_steps, dt)

    # 日次にダウンサンプル (100 step ごと)
    daily_a = traj_a[::100, 0]  # x 座標を日次リターン素材として
    daily_b = traj_b[::100, 0]
    n_days = min(len(daily_a), len(daily_b))
    daily_a = daily_a[:n_days]
    daily_b = daily_b[:n_days]

    # 日次リターンとして使う前にスケール: |x| が ~20 程度なので、/1000 して ±2%相当に
    daily_ret_a = daily_a / 1000.0
    daily_ret_b = daily_b / 1000.0

    # 複利
    equity_a = np.cumprod(1 + daily_ret_a)
    equity_b = np.cumprod(1 + daily_ret_b)

    # 軌跡発散の最初の日 (相対誤差 > 10%)
    diff = np.abs(equity_a - equity_b) / np.maximum(np.abs(equity_a), np.abs(equity_b))
    diverge_day = int(np.argmax(diff > 0.1)) if (diff > 0.1).any() else n_days

    # 相関係数 (全期間 vs 後半)
    corr_full = float(np.corrcoef(daily_ret_a, daily_ret_b)[0, 1])
    half = n_days // 2
    corr_first = float(np.corrcoef(daily_ret_a[:half], daily_ret_b[:half])[0, 1])
    corr_last = float(np.corrcoef(daily_ret_a[half:], daily_ret_b[half:])[0, 1])

    print(f'結果:')
    print(f'  日数: {n_days}')
    print(f'  系列 A 最終リターン: {(equity_a[-1] - 1)*100:+.2f}%')
    print(f'  系列 B 最終リターン: {(equity_b[-1] - 1)*100:+.2f}%')
    print(f'  10% 発散到達日: Day {diverge_day}')
    print(f'  相関係数 (全期間): {corr_full:+.4f}')
    print(f'  相関係数 (前半):   {corr_first:+.4f}')
    print(f'  相関係数 (後半):   {corr_last:+.4f}')
    print()

    out_dir = REPO_ROOT / 'results' / '012'
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        'config': {
            'experiment': 'Ep12: Lorenz カオスシミュレーション',
            'system': 'Lorenz (sigma=10, rho=28, beta=8/3)',
            'dt': dt,
            'n_days': n_days,
            'initial_a': init_a.tolist(),
            'initial_b': init_b.tolist(),
            'initial_diff_pct': perturb_pct * 100,
        },
        'results': {
            'final_return_a_pct': float((equity_a[-1] - 1)*100),
            'final_return_b_pct': float((equity_b[-1] - 1)*100),
            'final_return_diff_pct': float(abs(equity_a[-1] - equity_b[-1])/equity_a[-1] * 100),
            'first_10pct_diverge_day': diverge_day,
            'correlation_full': corr_full,
            'correlation_first_half': corr_first,
            'correlation_last_half': corr_last,
        },
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    # equity 軌跡を CSV 保存
    import pandas as pd
    pd.DataFrame({
        'day': range(n_days),
        'equity_a': equity_a,
        'equity_b': equity_b,
        'diff_pct': diff * 100,
    }).to_csv(out_dir / 'lorenz_trajectories.csv', index=False)
    print(f'保存: {out_dir}/summary.json + lorenz_trajectories.csv')
    return 0


if __name__ == '__main__':
    sys.exit(main())
