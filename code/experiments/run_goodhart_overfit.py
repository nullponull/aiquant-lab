"""Ep9: グッドハートの罠を grid search 過剰最適化で実証

設計:
  - Ep7 戦略の中から「最適化余地が大きいもの」を選ぶ (SMA Cross, RSI, MACD, Bollinger)
  - 各戦略のパラメータを直近 30 日で grid search → 最良パラメータを抽出
  - その最良パラメータで「次の 30 日 (= out-of-sample)」を予測
  - in-sample と out-of-sample のリターン差を計測

主張:
  in-sample 最良パラメータは out-of-sample で性能が落ちる = グッドハート

出力:
  results/009/summary.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from itertools import product

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / 'code'))

import pandas as pd
import numpy as np

from strategies.base import backtest, fetch_spy_data
from strategies.strategies import sma_cross, rsi_mean_reversion, macd_cross, bollinger_revert


def grid_search_sma(df: pd.DataFrame) -> tuple[dict, float]:
    """SMA Cross の (fast, slow) grid"""
    best = None
    best_ret = -999
    for fast in [5, 10, 15, 20, 25, 30]:
        for slow in [40, 50, 60, 80, 100]:
            if fast >= slow:
                continue
            sig = sma_cross(df, fast=fast, slow=slow)
            r = backtest(f'SMA-{fast}-{slow}', df, sig).total_return
            if r > best_ret:
                best_ret = r
                best = {'fast': fast, 'slow': slow}
    return best, best_ret


def grid_search_rsi(df: pd.DataFrame) -> tuple[dict, float]:
    best = None
    best_ret = -999
    for period in [7, 10, 14, 20]:
        for os_thresh, ob_thresh in [(20, 80), (25, 75), (30, 70), (35, 65)]:
            sig = rsi_mean_reversion(df, period=period, oversold=os_thresh, overbought=ob_thresh)
            r = backtest(f'RSI-{period}-{os_thresh}-{ob_thresh}', df, sig).total_return
            if r > best_ret:
                best_ret = r
                best = {'period': period, 'oversold': os_thresh, 'overbought': ob_thresh}
    return best, best_ret


def grid_search_macd(df: pd.DataFrame) -> tuple[dict, float]:
    best = None
    best_ret = -999
    for fast in [8, 12, 16]:
        for slow in [20, 26, 30]:
            for signal in [7, 9, 11]:
                if fast >= slow:
                    continue
                sig = macd_cross(df, fast=fast, slow=slow, signal_period=signal)
                r = backtest(f'MACD-{fast}-{slow}-{signal}', df, sig).total_return
                if r > best_ret:
                    best_ret = r
                    best = {'fast': fast, 'slow': slow, 'signal_period': signal}
    return best, best_ret


def grid_search_bollinger(df: pd.DataFrame) -> tuple[dict, float]:
    best = None
    best_ret = -999
    for period in [10, 15, 20, 25]:
        for n_std in [1.5, 2.0, 2.5, 3.0]:
            sig = bollinger_revert(df, period=period, n_std=n_std)
            r = backtest(f'BB-{period}-{n_std}', df, sig).total_return
            if r > best_ret:
                best_ret = r
                best = {'period': period, 'n_std': n_std}
    return best, best_ret


GRID_FUNCS = {
    'SMA-Cross': grid_search_sma,
    'RSI-Mean-Revert': grid_search_rsi,
    'MACD-Cross': grid_search_macd,
    'Bollinger-Revert': grid_search_bollinger,
}


def apply_with_best(name: str, df: pd.DataFrame, params: dict) -> float:
    """最良パラメータで out-of-sample に適用"""
    if name == 'SMA-Cross':
        sig = sma_cross(df, **params)
    elif name == 'RSI-Mean-Revert':
        sig = rsi_mean_reversion(df, **params)
    elif name == 'MACD-Cross':
        sig = macd_cross(df, **params)
    elif name == 'Bollinger-Revert':
        sig = bollinger_revert(df, **params)
    else:
        return 0.0
    return backtest(name, df, sig).total_return


def main() -> int:
    print('=== Ep9: グッドハートの罠 — Grid search 過剰最適化 ===')
    print()
    print('60 日 SPY 取得中...', flush=True)
    df_full = fetch_spy_data(period_days=120)  # 60 in-sample + 60 out-of-sample
    print(f'  取得: {len(df_full)} 日')

    half = len(df_full) // 2
    df_in = df_full.iloc[:half]
    df_out = df_full.iloc[half:]
    print(f'  in-sample:  {df_in.index[0].date()} → {df_in.index[-1].date()} ({len(df_in)} 日)')
    print(f'  out-of-sample: {df_out.index[0].date()} → {df_out.index[-1].date()} ({len(df_out)} 日)')
    print()

    print(f'{"strategy":<22} {"best params":<35} {"IS ret%":>10} {"OOS ret%":>10} {"diff":>10}')
    print('-' * 90)
    results = []
    for name, fn in GRID_FUNCS.items():
        best_params, is_ret = fn(df_in)
        oos_ret = apply_with_best(name, df_out, best_params)
        diff = oos_ret - is_ret
        params_str = ', '.join(f'{k}={v}' for k, v in best_params.items())
        print(f'{name:<22} {params_str:<35} {is_ret*100:+9.2f}  {oos_ret*100:+9.2f}  {diff*100:+9.2f}')
        results.append({
            'strategy': name,
            'best_params': best_params,
            'in_sample_return_pct': is_ret * 100,
            'out_of_sample_return_pct': oos_ret * 100,
            'difference_pct': diff * 100,
            'overfit_severity': 'severe' if diff < -0.05 else ('moderate' if diff < 0 else 'no'),
        })

    print()
    avg_is = np.mean([r['in_sample_return_pct'] for r in results])
    avg_oos = np.mean([r['out_of_sample_return_pct'] for r in results])
    print(f'平均 IS リターン:  {avg_is:+.2f}%')
    print(f'平均 OOS リターン: {avg_oos:+.2f}%')
    print(f'平均ギャップ:      {avg_oos - avg_is:+.2f}%')
    print()

    out_dir = REPO_ROOT / 'results' / '009'
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        'config': {
            'experiment': 'Ep9: グッドハート — grid search 過剰最適化',
            'symbol': 'SPY',
            'in_sample_period': f'{df_in.index[0].date()} → {df_in.index[-1].date()}',
            'out_of_sample_period': f'{df_out.index[0].date()} → {df_out.index[-1].date()}',
        },
        'strategies': results,
        'summary': {
            'avg_in_sample_pct': avg_is,
            'avg_out_of_sample_pct': avg_oos,
            'avg_gap_pct': avg_oos - avg_is,
            'severe_overfit_count': sum(1 for r in results if r['overfit_severity'] == 'severe'),
        },
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f'保存: {out_dir}/summary.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
