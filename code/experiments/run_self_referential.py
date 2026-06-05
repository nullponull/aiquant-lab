"""Ep13: 自己言及性 — エージェント大量取引で市場価格が AI の予測を含み始める

設計:
  - N 個のエージェントが「過去 20 日のモメンタム」で取引判断
  - 各取引が次期価格にインパクトを与える (Kyle's lambda 風)
  - 500 step シミュレーション、エージェント数を変えて比較
  - フィードバック効果を観測

主張:
  AI agent が増えると、価格はエージェントの予測を反映し始め、
  外部情報よりエージェント集団のロジックが支配的になる。

出力:
  results/013/summary.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]


def simulate_market(
    n_agents: int,
    n_steps: int = 500,
    initial_price: float = 100.0,
    impact_per_trade: float = 0.0001,  # 1 取引あたり価格に 0.01% impact
    fundamental_noise_std: float = 0.005,  # 0.5%/step のファンダメンタル変動
    momentum_window: int = 20,
    seed: int = 42,
) -> dict:
    """N agents の momentum 戦略でフィードバック市場シミュレーション"""
    rng = np.random.default_rng(seed)

    # 価格時系列
    prices = np.zeros(n_steps)
    prices[0] = initial_price

    # ファンダメンタル価値 (random walk)
    fundamentals = np.zeros(n_steps)
    fundamentals[0] = initial_price
    fund_shocks = rng.normal(0, fundamental_noise_std, n_steps)

    # 各 step
    for t in range(1, n_steps):
        # ファンダメンタル更新 (independent random walk)
        fundamentals[t] = fundamentals[t-1] * (1 + fund_shocks[t])

        # momentum signal (過去 momentum_window 日の方向)
        if t > momentum_window:
            mom = (prices[t-1] - prices[t-1-momentum_window]) / prices[t-1-momentum_window]
        else:
            mom = 0.0

        # 全エージェントが同じ判断 (Long if mom > 0, Short if mom < 0)
        # 強度は |mom| × 各エージェント
        net_demand = np.sign(mom) * abs(mom) * n_agents

        # 価格 = ファンダメンタル × (1 + agent impact)
        agent_impact = net_demand * impact_per_trade
        # 価格はファンダメンタルと agent impact の和 (シンプルな線形モデル)
        prices[t] = fundamentals[t] * (1 + agent_impact)

    # 結果
    fund_returns = np.diff(fundamentals) / fundamentals[:-1]
    price_returns = np.diff(prices) / prices[:-1]

    # ファンダメンタルと price の相関
    corr_fund_price = float(np.corrcoef(fund_returns, price_returns)[0, 1])

    # price returns の autocorrelation (lag 1) — momentum feedback が強いと正
    autocorr_lag1 = float(np.corrcoef(price_returns[:-1], price_returns[1:])[0, 1])

    # 価格とファンダメンタルの累積乖離
    final_divergence_pct = float((prices[-1] - fundamentals[-1]) / fundamentals[-1] * 100)

    return {
        'n_agents': n_agents,
        'corr_fund_price': corr_fund_price,
        'autocorr_lag1': autocorr_lag1,
        'final_divergence_pct': final_divergence_pct,
        'price_final': float(prices[-1]),
        'fundamental_final': float(fundamentals[-1]),
        'price_volatility_pct': float(price_returns.std() * 100),
        'fundamental_volatility_pct': float(fund_returns.std() * 100),
    }


def main() -> int:
    print('=== Ep13: 自己言及性 — エージェント数 vs フィードバック効果 ===')
    print()

    agent_counts = [0, 10, 100, 1000, 10000, 100000]
    print(f'{"agents":>8} {"corr(fund,price)":>17} {"autocorr_lag1":>15} {"divergence%":>12} {"price_vol%":>11}')
    print('-' * 75)
    results = []
    for n in agent_counts:
        result = simulate_market(n_agents=n)
        results.append(result)
        print(f'{n:>8} {result["corr_fund_price"]:>17.4f} {result["autocorr_lag1"]:>15.4f} {result["final_divergence_pct"]:>+11.2f}  {result["price_volatility_pct"]:>10.3f}')

    print()
    print('読み取り方:')
    print('  corr(fund,price) = 1.0  → ファンダメンタルだけで価格が決まる')
    print('  corr(fund,price) < 0.5  → エージェント集団のロジックが価格を支配')
    print('  autocorr_lag1 > 0        → モメンタムの自己実現フィードバック')
    print()

    out_dir = REPO_ROOT / 'results' / '013'
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        'config': {
            'experiment': 'Ep13: 自己言及性 — エージェント大量取引のフィードバック',
            'n_steps': 500,
            'impact_per_trade': 0.0001,
            'fundamental_noise_std': 0.005,
            'momentum_window': 20,
            'seed': 42,
        },
        'simulations': results,
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'保存: {out_dir}/summary.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
