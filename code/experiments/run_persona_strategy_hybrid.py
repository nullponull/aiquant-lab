"""Ep16 (番外編 #4): 2,245 ペルソナ × 10 戦略 = 22,450 通りの投資反応シミュレーション

設計:
  - 2,245 ペルソナ (Persona API データ) を模擬: risk_tolerance × time_horizon × sophistication の 3 軸でサンプリング
  - 10 戦略 (Ep7) の特性に基づいて、各ペルソナの戦略選好スコアを計算
  - 層別 (risk_low/mid/high × horizon_short/long) で勝率と期待 PnL を比較

主張:
  同じ戦略を平均値で評価すると見落とす層別効果がある。
  Persona × Strategy は新規の検証次元を提供する。

出力:
  results/016/summary.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]


# Ep7 の 10 戦略の「特性ベクトル」 — どんなペルソナが好むか
STRATEGY_PROFILES = {
    'Buy-and-Hold':      {'risk': 0.2, 'horizon': 1.0, 'sophistication': 0.1},
    'SMA-Cross-20-50':   {'risk': 0.4, 'horizon': 0.6, 'sophistication': 0.4},
    'RSI-Mean-Revert':   {'risk': 0.6, 'horizon': 0.3, 'sophistication': 0.5},
    'MACD-Cross':        {'risk': 0.5, 'horizon': 0.5, 'sophistication': 0.5},
    'Momentum-20d':      {'risk': 0.5, 'horizon': 0.4, 'sophistication': 0.3},
    'Bollinger-Revert':  {'risk': 0.6, 'horizon': 0.3, 'sophistication': 0.6},
    'Donchian-Breakout': {'risk': 0.7, 'horizon': 0.4, 'sophistication': 0.6},
    'Volume-Spike':      {'risk': 0.8, 'horizon': 0.2, 'sophistication': 0.7},
    'Z-Score-Revert':    {'risk': 0.6, 'horizon': 0.3, 'sophistication': 0.6},
    'Random-Control':    {'risk': 0.9, 'horizon': 0.1, 'sophistication': 0.0},
}

# Ep7 の実 30 日結果 (期待 PnL の base)
STRATEGY_PNL_PCT = {
    'Buy-and-Hold':      +6.81,
    'SMA-Cross-20-50':   +2.09,
    'RSI-Mean-Revert':   -3.56,
    'MACD-Cross':        +1.54,
    'Momentum-20d':      +6.81,
    'Bollinger-Revert':  +0.00,
    'Donchian-Breakout': -1.12,
    'Volume-Spike':      +0.00,
    'Z-Score-Revert':    -0.91,
    'Random-Control':    -2.11,
}


def sample_personas(n: int = 2245, seed: int = 42) -> pd.DataFrame:
    """Persona API の 2,245 体を模擬: 3 軸サンプリング"""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        'persona_id': [f'P-{i:04d}' for i in range(n)],
        'risk_tolerance': rng.beta(2, 5, n),       # 多くが低リスク
        'time_horizon': rng.beta(3, 2, n),         # 多くが長期志向
        'sophistication': rng.beta(2, 3, n),       # 多くが初級〜中級
    })
    return df


def strategy_preference_score(persona: pd.Series, strat_profile: dict) -> float:
    """ペルソナと戦略のマッチング度 (0〜1)"""
    # 各軸の差の二乗を足して 1 - sqrt にして類似度に
    diff_sq = (
        (persona['risk_tolerance'] - strat_profile['risk']) ** 2 +
        (persona['time_horizon'] - strat_profile['horizon']) ** 2 +
        (persona['sophistication'] - strat_profile['sophistication']) ** 2
    )
    similarity = 1 - (diff_sq / 3) ** 0.5
    return float(np.clip(similarity, 0, 1))


def main() -> int:
    print('=== Ep16: Persona × Strategy 22,450 通りシミュレーション ===')
    print()
    personas = sample_personas(n=2245)
    print(f'ペルソナ: {len(personas)} 体')
    print(f'戦略:     {len(STRATEGY_PROFILES)}')
    print(f'組み合わせ: {len(personas) * len(STRATEGY_PROFILES)} 通り')
    print()

    # 全 22,450 マッチング
    rows = []
    for _, p in personas.iterrows():
        for strat_name, profile in STRATEGY_PROFILES.items():
            score = strategy_preference_score(p, profile)
            # 期待 PnL: マッチング度が高いほど、結果が出やすい
            # (低マッチングは集中投資できず希釈される想定)
            expected_pnl_pct = STRATEGY_PNL_PCT[strat_name] * (0.5 + 0.5 * score)
            rows.append({
                'persona_id': p['persona_id'],
                'risk_tolerance': p['risk_tolerance'],
                'time_horizon': p['time_horizon'],
                'sophistication': p['sophistication'],
                'strategy': strat_name,
                'preference_score': score,
                'expected_pnl_pct': expected_pnl_pct,
            })

    df = pd.DataFrame(rows)
    print(f'全マッチング: {len(df)} 行')
    print()

    # 層別: risk_tolerance の 3 分位 × 各戦略の平均期待 PnL
    df['risk_bucket'] = pd.qcut(df['risk_tolerance'], 3, labels=['low', 'mid', 'high'])
    df['horizon_bucket'] = pd.qcut(df['time_horizon'], 2, labels=['short', 'long'])

    print('=== risk_bucket × strategy の平均期待 PnL ===')
    pivot = df.pivot_table(index='strategy', columns='risk_bucket', values='expected_pnl_pct', aggfunc='mean', observed=True)
    print(pivot.round(2))
    print()

    # 戦略 × 層別ごとの最良ペルソナ層
    print('=== 各戦略の最適ペルソナ層 (risk × horizon) ===')
    best_segments = []
    for strat in STRATEGY_PROFILES.keys():
        sdf = df[df['strategy'] == strat]
        seg = sdf.groupby(['risk_bucket', 'horizon_bucket'], observed=True)['expected_pnl_pct'].mean()
        best_idx = seg.idxmax()
        worst_idx = seg.idxmin()
        diff = seg.max() - seg.min()
        best_segments.append({
            'strategy': strat,
            'best_segment': f'{best_idx[0]}-{best_idx[1]}',
            'best_pnl_pct': float(seg.max()),
            'worst_segment': f'{worst_idx[0]}-{worst_idx[1]}',
            'worst_pnl_pct': float(seg.min()),
            'spread': float(diff),
        })
        print(f'  {strat:<22} best={best_idx} ({seg.max():+.2f}%)  worst={worst_idx} ({seg.min():+.2f}%)  spread={diff:.2f}')
    print()

    # 集計
    overall_best = max(best_segments, key=lambda x: x['best_pnl_pct'])
    overall_worst = min(best_segments, key=lambda x: x['worst_pnl_pct'])
    avg_spread = float(np.mean([s['spread'] for s in best_segments]))
    print(f'全体最良: {overall_best["strategy"]} ({overall_best["best_segment"]}, {overall_best["best_pnl_pct"]:+.2f}%)')
    print(f'全体最悪: {overall_worst["strategy"]} ({overall_worst["worst_segment"]}, {overall_worst["worst_pnl_pct"]:+.2f}%)')
    print(f'平均ペルソナ層別スプレッド: {avg_spread:.2f}%')

    # 保存
    out_dir = REPO_ROOT / 'results' / '016'
    out_dir.mkdir(parents=True, exist_ok=True)
    df.head(500).to_csv(out_dir / 'persona_strategy_sample.csv', index=False)
    pivot.to_csv(out_dir / 'risk_strategy_pivot.csv')
    summary = {
        'config': {
            'experiment': 'Ep16: Persona × Strategy hybrid',
            'n_personas': len(personas),
            'n_strategies': len(STRATEGY_PROFILES),
            'n_combinations': len(df),
        },
        'best_segments': best_segments,
        'overall_best': overall_best,
        'overall_worst': overall_worst,
        'avg_segment_spread_pct': avg_spread,
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'保存: {out_dir}/summary.json + risk_strategy_pivot.csv')
    return 0


if __name__ == '__main__':
    sys.exit(main())
