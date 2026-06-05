"""Ep11: 10 年 vs 直近 1 年の SPY リターン分布比較

主張: バックテストの数字は信頼できない理由を「分布が違う」で示す.

出力:
  results/011/distribution_summary.json
  results/011/distribution_table.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / 'code'))

import numpy as np
import pandas as pd


def fetch(symbol: str, period: str) -> pd.DataFrame:
    import yfinance as yf
    return yf.Ticker(symbol).history(period=period, auto_adjust=True)


def describe(returns: pd.Series, label: str) -> dict:
    r = returns.dropna()
    if len(r) == 0:
        return {'label': label, 'n': 0}

    sorted_r = np.sort(r.values)
    n = len(r)
    out = {
        'label': label,
        'n': int(n),
        'mean_pct': float(r.mean() * 100),
        'std_pct': float(r.std() * 100),
        'skew': float(r.skew()),
        'kurtosis': float(r.kurtosis()),  # excess kurtosis
        'min_pct': float(r.min() * 100),
        'max_pct': float(r.max() * 100),
        'p01_pct': float(np.percentile(sorted_r, 1) * 100),
        'p05_pct': float(np.percentile(sorted_r, 5) * 100),
        'p50_pct': float(np.percentile(sorted_r, 50) * 100),
        'p95_pct': float(np.percentile(sorted_r, 95) * 100),
        'p99_pct': float(np.percentile(sorted_r, 99) * 100),
        # 大きい片側の発生頻度
        'days_lt_minus2pct': int((r < -0.02).sum()),
        'days_gt_plus2pct': int((r > 0.02).sum()),
        'days_lt_minus5pct': int((r < -0.05).sum()),
    }
    out['ratio_days_lt_minus2pct'] = out['days_lt_minus2pct'] / n
    return out


def normality_test(returns: pd.Series, label: str) -> dict:
    """正規分布テスト (Jarque-Bera + Shapiro-Wilk)"""
    from scipy import stats
    r = returns.dropna().values
    if len(r) < 20:
        return {'label': label, 'tests': 'insufficient_data'}
    jb_stat, jb_p = stats.jarque_bera(r)
    sw_stat, sw_p = stats.shapiro(r[:5000])  # Shapiro-Wilk は n<=5000
    return {
        'label': label,
        'jarque_bera_stat': float(jb_stat),
        'jarque_bera_p': float(jb_p),
        'jarque_bera_reject_normality': bool(jb_p < 0.05),
        'shapiro_wilk_stat': float(sw_stat),
        'shapiro_wilk_p': float(sw_p),
        'shapiro_wilk_reject_normality': bool(sw_p < 0.05),
    }


def main() -> int:
    print('=== Ep11: SPY リターン分布シフト分析 (10 年 vs 直近 1 年) ===')
    print()

    # 10 年データ
    print('10 年データ取得中...', flush=True)
    df10y = fetch('SPY', '10y')
    df10y['ret'] = df10y['Close'].pct_change()
    print(f'  取得: {len(df10y)} 日 ({df10y.index[0].date()} → {df10y.index[-1].date()})')

    # 直近 1 年データ
    print('1 年データ取得中...', flush=True)
    df1y = df10y.tail(252).copy()
    print(f'  直近 1 年: {len(df1y)} 日 ({df1y.index[0].date()} → {df1y.index[-1].date()})')

    # 比較対象: 10 年 (全期間) vs 直近 1 年
    desc10 = describe(df10y['ret'], '過去 10 年 (2017→2026)')
    desc1 = describe(df1y['ret'], '直近 1 年 (2025→2026)')

    # 直近 1 年を除く 9 年 (旧 9 年)
    df9y_old = df10y.iloc[:-252]
    desc9 = describe(df9y_old['ret'], '旧 9 年 (2017→2025)')

    print()
    print('=' * 78)
    print(f'{"指標":<25} {"10年":>15} {"旧9年":>15} {"直近1年":>15}')
    print('=' * 78)
    keys = [
        ('n (営業日)', 'n'),
        ('平均%/日', 'mean_pct'),
        ('std%/日', 'std_pct'),
        ('歪度 (skew)', 'skew'),
        ('尖度 (kurt)', 'kurtosis'),
        ('-1% < min', 'min_pct'),
        ('+1% > max', 'max_pct'),
        ('1%ile (%)', 'p01_pct'),
        ('5%ile (%)', 'p05_pct'),
        ('95%ile (%)', 'p95_pct'),
        ('99%ile (%)', 'p99_pct'),
        ('-2% 以下の日数', 'days_lt_minus2pct'),
        ('+2% 以上の日数', 'days_gt_plus2pct'),
        ('-5% 以下の日数', 'days_lt_minus5pct'),
    ]
    for label, key in keys:
        v10 = desc10.get(key, '-')
        v9 = desc9.get(key, '-')
        v1 = desc1.get(key, '-')
        if isinstance(v10, float):
            print(f'{label:<25} {v10:>15.3f} {v9:>15.3f} {v1:>15.3f}')
        else:
            print(f'{label:<25} {v10:>15} {v9:>15} {v1:>15}')
    print()

    # 正規性検定
    print('=' * 78)
    print('正規分布テスト (帰無仮説: 正規分布)')
    print('=' * 78)
    nt10 = normality_test(df10y['ret'], '10年')
    nt1 = normality_test(df1y['ret'], '直近1年')
    for nt in [nt10, nt1]:
        print(f'  {nt["label"]}:')
        print(f'    Jarque-Bera p={nt["jarque_bera_p"]:.6f}  → 正規性 {"棄却" if nt["jarque_bera_reject_normality"] else "棄却せず"}')
        print(f'    Shapiro-Wilk p={nt["shapiro_wilk_p"]:.6f}  → 正規性 {"棄却" if nt["shapiro_wilk_reject_normality"] else "棄却せず"}')
    print()

    # 保存
    out_dir = REPO_ROOT / 'results' / '011'
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        'config': {
            'experiment': 'Ep11: 10 年 vs 直近 1 年の SPY リターン分布シフト',
            'symbol': 'SPY',
            'period_long': '10y',
            'data_range_long': f'{df10y.index[0].date()} → {df10y.index[-1].date()}',
            'data_range_recent': f'{df1y.index[0].date()} → {df1y.index[-1].date()}',
        },
        'distributions': {
            '10_years': desc10,
            'old_9_years': desc9,
            'recent_1_year': desc1,
        },
        'normality_tests': {
            '10_years': nt10,
            'recent_1_year': nt1,
        },
    }
    (out_dir / 'distribution_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f'保存: {out_dir}/distribution_summary.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
