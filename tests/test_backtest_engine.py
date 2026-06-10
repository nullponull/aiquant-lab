"""バックテストエンジン (code/strategies/base.py) の単体テスト

特に重要なのは test_no_lookahead_*: シグナル確定後の価格変化が
その日のポジションに影響しない (= 未来情報を使えない) ことを検証する。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

from strategies.base import (  # noqa: E402
    backtest,
    segment_trades,
    COMMISSION,
    SLIPPAGE,
)


def make_df(closes, opens=None):
    idx = pd.bdate_range("2025-01-01", periods=len(closes))
    closes = pd.Series(closes, index=idx, dtype=float)
    if opens is None:
        opens = closes.shift(1).fillna(closes.iloc[0])
    else:
        opens = pd.Series(opens, index=idx, dtype=float)
    return pd.DataFrame({
        "open": opens,
        "high": np.maximum(opens, closes),
        "low": np.minimum(opens, closes),
        "close": closes,
        "volume": 1_000_000,
    })


# ---------------------------------------------------------------------------
# 基本動作
# ---------------------------------------------------------------------------
def test_buy_and_hold_next_close_matches_market_minus_costs():
    closes = [100, 101, 102, 103, 104, 105]
    df = make_df(closes)
    sig = pd.Series(1, index=df.index)
    res = backtest("bh", df, sig, execution="next_close",
                   commission=0.0, slippage=0.0)
    # day0 終値のシグナルが day1 以降のリターンを獲得: 100→105
    expected = 105 / 100 - 1
    assert res.total_return == pytest.approx(expected, rel=1e-9)
    assert res.n_trades == 1
    assert res.survival == "alive"


def test_costs_reduce_equity_by_expected_amount():
    closes = [100.0] * 10  # 価格は動かない
    df = make_df(closes)
    # 1 回だけ long → flat (往復 2 単位のポジション変化)
    sig = pd.Series(0, index=df.index)
    sig.iloc[2:5] = 1
    res = backtest("cost", df, sig, execution="next_close")
    per_side = COMMISSION + SLIPPAGE
    expected = (1 - per_side) * (1 - per_side) - 1  # エントリー + エグジット
    assert res.total_return == pytest.approx(expected, rel=1e-6)
    assert res.total_cost == pytest.approx(2 * per_side, rel=1e-6)


# ---------------------------------------------------------------------------
# ルックアヘッド検証
# ---------------------------------------------------------------------------
def test_no_lookahead_next_close():
    """day t のシグナルは day t のリターンを獲得できない (shift(1))"""
    closes = [100, 100, 100, 100, 120, 100, 100, 100]
    df = make_df(closes)
    # 「+20% の当日だけ long」という未来が見えていないと作れないシグナル
    sig = pd.Series(0, index=df.index)
    sig.iloc[4] = 1  # 100→120 の当日
    res = backtest("cheat", df, sig, execution="next_close",
                   commission=0.0, slippage=0.0)
    # shift(1) により実際に保有するのは翌日 (120→100) なので大損するはず
    assert res.total_return < -0.15


def test_no_lookahead_next_open_uses_two_day_lag():
    """next_open: day t のシグナルが効くのは open(t+1)→open(t+2) 区間"""
    opens = [100, 100, 100, 100, 100, 150, 100, 100]
    closes = opens
    df = make_df(closes, opens=opens)
    # day3 のシグナルで long → open(4)=100 で約定、open(5)=150 で評価 → +50%
    sig = pd.Series(0, index=df.index)
    sig.iloc[3] = 1
    res = backtest("lag", df, sig, execution="next_open",
                   commission=0.0, slippage=0.0)
    assert res.total_return == pytest.approx(0.50, rel=1e-9)

    # 同じ値動きでも day4 のシグナルでは open(5)→open(6) = 150→100 で -33%
    sig2 = pd.Series(0, index=df.index)
    sig2.iloc[4] = 1
    res2 = backtest("lag2", df, sig2, execution="next_open",
                    commission=0.0, slippage=0.0)
    assert res2.total_return == pytest.approx(100 / 150 - 1, rel=1e-9)


def test_future_price_change_does_not_affect_past_positions():
    """day t までの equity は day t+2 以降の価格に依存しない"""
    closes_a = [100, 101, 102, 103, 104, 105, 106, 107]
    closes_b = [100, 101, 102, 103, 104, 105, 200, 50]  # 末尾だけ改変
    sigs = lambda df: pd.Series([0, 1, 1, -1, -1, 0, 1, 1], index=df.index)  # noqa: E731

    res_a = backtest("a", make_df(closes_a), sigs(make_df(closes_a)),
                     execution="next_close", keep_trades=True)
    res_b = backtest("b", make_df(closes_b), sigs(make_df(closes_b)),
                     execution="next_close", keep_trades=True)
    # 改変前の区間 (day0-5) で閉じたトレードの成績は一致するはず
    closed_a = [t for t in res_a.trades if t["exit_date"] <= "2025-01-07"]
    closed_b = [t for t in res_b.trades if t["exit_date"] <= "2025-01-07"]
    assert closed_a == closed_b


# ---------------------------------------------------------------------------
# トレード分割
# ---------------------------------------------------------------------------
def test_trade_segmentation_counts_round_trips():
    idx = pd.bdate_range("2025-01-01", periods=8)
    pos = pd.Series([0, 1, 1, 0, -1, -1, 1, 0], index=idx)
    ret = pd.Series(0.01, index=idx)
    trades = segment_trades(pos, ret, ret)
    # long(2日), short(2日), long(1日) の 3 トレード
    assert len(trades) == 3
    assert [t.direction for t in trades] == [1, -1, 1]
    assert [t.n_days for t in trades] == [2, 2, 1]
    assert trades[0].net_return == pytest.approx(1.01 * 1.01 - 1, rel=1e-9)


def test_short_window_flags_annualization_unreliable():
    closes = list(100 + np.arange(30, dtype=float))
    df = make_df(closes)
    sig = pd.Series(1, index=df.index)
    res = backtest("short", df, sig)
    assert res.annualization_reliable is False
