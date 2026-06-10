"""Ep7: 10 戦略 × SPY 30 営業日 並列バックテスト

実行:
    uv run python3 code/experiments/run_10strategies_30days.py

出力:
    results/004/summary.json
    results/004/equity_curves.csv
    results/004/detail_<strategy>.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / 'code'))

import pandas as pd
from strategies.base import backtest, equity_curve, fetch_spy_data, save_results, COMMISSION, MIN_DAYS_FOR_ANNUALIZATION
from strategies.strategies import STRATEGIES


def main() -> int:
    print('=== Ep7: 10 戦略 × SPY 30 営業日 並列バックテスト ===')
    print()

    # データ取得 (60 日 = 30 営業日 + warm-up)
    print('SPY 60 日データ取得中...', flush=True)
    df_full = fetch_spy_data(period_days=60)
    print(f'  取得: {len(df_full)} 営業日 ({df_full.index[0].date()} → {df_full.index[-1].date()})')

    # 直近 30 営業日に切り出し
    if len(df_full) < 30:
        print(f'  ⚠️ データ不足 ({len(df_full)}) — 60日全部使用')
        df30 = df_full
        # warm-up 用に full は使い、評価窓を直近 30 にする方が安全
        full = df_full
    else:
        full = df_full
        df30 = df_full.tail(30)

    print(f'  評価窓: 直近 {len(df30)} 営業日')
    print(f'  期間ベースリターン (SPY): {(df30["close"].iloc[-1] / df30["close"].iloc[0] - 1)*100:+.2f}%')
    print()

    # 各戦略のシグナル生成 → full データで計算 → 評価窓に絞る
    results = []
    equity_curves = pd.DataFrame()
    out_dir = REPO_ROOT / 'results' / '004'
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'{"#":>3} {"strategy":<22} {"trades":>7} {"ret%":>8} {"sharpe":>7} {"max_dd%":>8} {"final¥":>11} {"生死":<8}')
    print('-' * 80)

    for i, (name, fn) in enumerate(STRATEGIES.items(), 1):
        # full データでシグナル
        signals_full = fn(full)
        # 評価窓に絞る
        evaluation_index = df30.index
        signals = signals_full.reindex(evaluation_index).fillna(0)

        result = backtest(name, df30, signals, execution='next_open')
        results.append(result)

        # equity curve を保存 (エンジンと同一ロジックを使用)
        equity = equity_curve(df30, signals, execution='next_open')
        equity_curves[name] = equity.values

        survival_icon = {
            'alive':   '✓ 生存',
            'wounded': '! 負傷',
            'dead':    '✗ 死亡',
        }[result.survival]

        print(f'{i:>3} {name:<22} {result.n_trades:>7} {result.total_return*100:+7.2f}  {result.sharpe:+6.2f}  {result.max_drawdown*100:+7.2f}  {result.final_equity_jpy:>10,d}  {survival_icon}')

    print('-' * 80)
    print()

    # 集計
    alive = sum(1 for r in results if r.survival == 'alive')
    wounded = sum(1 for r in results if r.survival == 'wounded')
    dead = sum(1 for r in results if r.survival == 'dead')
    total_loss = sum(r.final_equity_jpy - 1_000_000 for r in results)
    print(f'生存集計: ✓生存 {alive} / !負傷 {wounded} / ✗死亡 {dead}')
    print(f'10 戦略合計損益: ¥{total_loss:+,d}')
    if results and not results[0].annualization_reliable:
        print()
        print(f'⚠️  評価期間 {results[0].n_days} 営業日は統計的判断には短すぎます'
              f' (推奨 {MIN_DAYS_FOR_ANNUALIZATION} 営業日以上)。')
        print('   sharpe / 年率値は参考値であり、生死判定はノイズを含みます。')
        print('   有意性の評価には code/experiments/run_significance_audit.py を使ってください。')
    print()

    # 保存
    save_results(results, out_dir)
    equity_curves.index = df30.index
    equity_curves.to_csv(out_dir / 'equity_curves.csv')
    print(f'結果保存: {out_dir}/summary.json')
    print(f'         {out_dir}/equity_curves.csv')

    return 0


if __name__ == '__main__':
    sys.exit(main())
