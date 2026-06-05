"""10 戦略バックテストの共通基盤 (Ep7 用)

設計方針:
- 各戦略は (df) -> pd.Series (位置サイン: -1/0/+1) を返す関数
- 同一の backtest_engine で評価
- 取引コスト 0.05% (片道) を控除
- 30 日 (約 21 営業日) でメトリクス算出
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd


COMMISSION = 0.0005  # 片道 0.05% (Interactive Brokers 程度)
ANNUAL_TRADING_DAYS = 252


@dataclass
class StrategyResult:
    name: str
    n_days: int
    n_trades: int
    total_return: float           # 期間全体の累積リターン
    annualized_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float | None
    final_equity_jpy: int          # 100万円スタートで月末残高
    survival: str                  # alive / wounded / dead

    def to_dict(self) -> dict:
        return asdict(self)


def backtest(name: str, df: pd.DataFrame, signals: pd.Series, initial_jpy: int = 1_000_000) -> StrategyResult:
    """1 戦略の 30 日バックテスト.

    Args:
        df: 'close' カラムを含む価格 DataFrame
        signals: -1/0/+1 のポジションシグナル (index は df と同じ)
        initial_jpy: 開始資金
    """
    # 翌日始値で約定する想定で signals を 1 期遅らせる
    pos = signals.shift(1).fillna(0).clip(-1, 1)
    daily_ret = df['close'].pct_change().fillna(0)
    # ポジションあたり日次リターン
    strat_ret = pos * daily_ret
    # ポジション変化で取引コスト
    trade_changes = pos.diff().abs().fillna(0)
    cost = trade_changes * COMMISSION
    strat_ret_after_cost = strat_ret - cost

    equity = (1 + strat_ret_after_cost).cumprod()
    total_return = float(equity.iloc[-1] - 1.0) if len(equity) else 0.0

    n_days = len(equity)
    # 年率化
    if n_days > 0:
        annualized = (1 + total_return) ** (ANNUAL_TRADING_DAYS / n_days) - 1
    else:
        annualized = 0.0

    # Sharpe (risk-free 0)
    mean_ret = strat_ret_after_cost.mean()
    std_ret = strat_ret_after_cost.std()
    sharpe = float(mean_ret / std_ret * math.sqrt(ANNUAL_TRADING_DAYS)) if std_ret > 0 else 0.0

    # Max drawdown
    cummax = equity.cummax()
    dd = (equity / cummax - 1.0)
    max_dd = float(dd.min()) if len(dd) else 0.0

    # トレード数 (ポジションが 0 ↔ 非0 に変わった回数の半分)
    n_trades = int(trade_changes.gt(0).sum())

    # 勝率: トレード単位で計算 (近似: ポジ反転ごとに区切る)
    # 簡易: pos>0 の日のリターンが正の比率
    long_days = strat_ret_after_cost[pos > 0]
    short_days = strat_ret_after_cost[pos < 0]
    active = pd.concat([long_days, short_days])
    win_rate = float((active > 0).mean()) if len(active) > 0 else None

    final_equity = int(initial_jpy * float(equity.iloc[-1])) if len(equity) else initial_jpy

    # 生存判定: 評価指標 = total_return >= 0 → alive, -10% 未満 → dead, それ以外 wounded
    if total_return >= 0:
        survival = 'alive'
    elif total_return >= -0.10:
        survival = 'wounded'
    else:
        survival = 'dead'

    return StrategyResult(
        name=name,
        n_days=n_days,
        n_trades=n_trades,
        total_return=float(total_return),
        annualized_return=float(annualized),
        sharpe=sharpe,
        max_drawdown=max_dd,
        win_rate=win_rate,
        final_equity_jpy=final_equity,
        survival=survival,
    )


def fetch_spy_data(period_days: int = 60) -> pd.DataFrame:
    """SPY の直近データを yfinance から取得 (期間は warm-up 込み).

    Returns:
        DataFrame with columns: close, high, low, open, volume
    """
    import yfinance as yf
    ticker = yf.Ticker('SPY')
    # 直近 60 日 (warm-up 用) 取得して、後で 30 日に切り出す
    df = ticker.history(period=f'{period_days}d', auto_adjust=True)
    df.columns = [c.lower() for c in df.columns]
    return df[['open', 'high', 'low', 'close', 'volume']]


def save_results(results: list[StrategyResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        'config': {
            'experiment': 'Ep7: 10 戦略 30 日並列バックテスト',
            'symbol': 'SPY',
            'initial_capital_jpy': 1_000_000,
            'commission': COMMISSION,
        },
        'strategies': [r.to_dict() for r in results],
        'summary': {
            'alive': sum(1 for r in results if r.survival == 'alive'),
            'wounded': sum(1 for r in results if r.survival == 'wounded'),
            'dead': sum(1 for r in results if r.survival == 'dead'),
        },
    }
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
