"""10 戦略の実装 (Ep7 用)

各戦略は (df: pd.DataFrame) -> pd.Series を返す関数として定義する。
シグナルは {-1: short, 0: flat, +1: long} のいずれか。

戦略リスト:
1. Buy-and-Hold (control)
2. SMA Golden Cross (50 vs 200) — 古典トレンドフォロー
3. RSI Mean Reversion (14)
4. MACD Cross
5. Momentum 12-month
6. Bollinger Band Squeeze
7. Donchian Channel Breakout (20)
8. Volume Spike + Price Up
9. Pair Trade (SPY vs QQQ proxy: use rolling z-score)
10. Random Control (シード固定で再現性確保)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. Buy-and-Hold (control)
# ---------------------------------------------------------------------------
def buy_and_hold(df: pd.DataFrame) -> pd.Series:
    return pd.Series(1, index=df.index)


# ---------------------------------------------------------------------------
# 2. SMA Golden Cross
# ---------------------------------------------------------------------------
def sma_cross(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    sma_f = df['close'].rolling(fast).mean()
    sma_s = df['close'].rolling(slow).mean()
    sig = pd.Series(0, index=df.index)
    sig[sma_f > sma_s] = 1
    sig[sma_f < sma_s] = -1
    return sig


# ---------------------------------------------------------------------------
# 3. RSI Mean Reversion
# ---------------------------------------------------------------------------
def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_g = gain.rolling(period).mean()
    avg_l = loss.rolling(period).mean()
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def rsi_mean_reversion(df: pd.DataFrame, period: int = 14, oversold: int = 30, overbought: int = 70) -> pd.Series:
    r = rsi(df['close'], period)
    sig = pd.Series(0, index=df.index)
    sig[r < oversold] = 1
    sig[r > overbought] = -1
    return sig


# ---------------------------------------------------------------------------
# 4. MACD Cross
# ---------------------------------------------------------------------------
def macd_cross(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal_period: int = 9) -> pd.Series:
    ema_f = df['close'].ewm(span=fast, adjust=False).mean()
    ema_s = df['close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_f - ema_s
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    sig = pd.Series(0, index=df.index)
    sig[macd_line > signal_line] = 1
    sig[macd_line < signal_line] = -1
    return sig


# ---------------------------------------------------------------------------
# 5. 12-month Momentum (proxy for short window: 20 営業日)
# ---------------------------------------------------------------------------
def momentum_short(df: pd.DataFrame, look: int = 20) -> pd.Series:
    ret = df['close'].pct_change(look)
    sig = pd.Series(0, index=df.index)
    sig[ret > 0.01] = 1   # 直近 20 日で +1% 以上なら long
    sig[ret < -0.01] = -1
    return sig


# ---------------------------------------------------------------------------
# 6. Bollinger Band Mean Reversion
# ---------------------------------------------------------------------------
def bollinger_revert(df: pd.DataFrame, period: int = 20, n_std: float = 2.0) -> pd.Series:
    ma = df['close'].rolling(period).mean()
    sd = df['close'].rolling(period).std()
    upper = ma + n_std * sd
    lower = ma - n_std * sd
    sig = pd.Series(0, index=df.index)
    sig[df['close'] < lower] = 1
    sig[df['close'] > upper] = -1
    return sig


# ---------------------------------------------------------------------------
# 7. Donchian Channel Breakout
# ---------------------------------------------------------------------------
def donchian_breakout(df: pd.DataFrame, period: int = 20) -> pd.Series:
    upper = df['high'].rolling(period).max()
    lower = df['low'].rolling(period).min()
    sig = pd.Series(0, index=df.index)
    sig[df['close'] >= upper.shift(1)] = 1
    sig[df['close'] <= lower.shift(1)] = -1
    return sig


# ---------------------------------------------------------------------------
# 8. Volume Spike + Price Up
# ---------------------------------------------------------------------------
def volume_spike(df: pd.DataFrame, period: int = 20, k: float = 1.5) -> pd.Series:
    vol_mean = df['volume'].rolling(period).mean()
    daily_ret = df['close'].pct_change()
    sig = pd.Series(0, index=df.index)
    spike = (df['volume'] > k * vol_mean) & (daily_ret > 0)
    sig[spike] = 1
    return sig


# ---------------------------------------------------------------------------
# 9. Z-Score Mean Reversion (Pair trade のサロゲート)
# ---------------------------------------------------------------------------
def zscore_revert(df: pd.DataFrame, period: int = 20, threshold: float = 1.5) -> pd.Series:
    ma = df['close'].rolling(period).mean()
    sd = df['close'].rolling(period).std()
    z = (df['close'] - ma) / sd
    sig = pd.Series(0, index=df.index)
    sig[z > threshold] = -1   # 上に外れた → short
    sig[z < -threshold] = 1   # 下に外れた → long
    return sig


# ---------------------------------------------------------------------------
# 10. Random Control (再現性のため seed 固定)
# ---------------------------------------------------------------------------
def random_control(df: pd.DataFrame, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    sig = pd.Series(rng.choice([-1, 0, 1], size=len(df), p=[0.3, 0.4, 0.3]),
                    index=df.index)
    return sig


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
STRATEGIES = {
    'Buy-and-Hold':        buy_and_hold,
    'SMA-Cross-20-50':     sma_cross,
    'RSI-Mean-Revert':     rsi_mean_reversion,
    'MACD-Cross':          macd_cross,
    'Momentum-20d':        momentum_short,
    'Bollinger-Revert':    bollinger_revert,
    'Donchian-Breakout':   donchian_breakout,
    'Volume-Spike':        volume_spike,
    'Z-Score-Revert':      zscore_revert,
    'Random-Control':      random_control,
}
