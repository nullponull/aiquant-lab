"""クロスセクショナル・ランキング予測 (Phase 3c)

「SPY が明日上がるか」(時系列・単一銘柄) より「数百銘柄のうち
どれが相対的に強いか」(クロスセクション) の方が、ノイズが平均化され
統計的検出力が桁違いに高い。機関クオンツの主戦場はこちら。

評価は Rank IC (Information Coefficient):
    IC(t) = Spearman相関( シグナル(t), 次期間リターン(t→t+h) )
IC の時系列平均と t 統計量 (Newey-West) で「ランキングに予測力があるか」
を判定する。|mean IC| が 0.02-0.05 でも実務的には十分大きい。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# シグナル (例: 12-1 モメンタム)
# ---------------------------------------------------------------------------
def momentum_12_1(prices: pd.DataFrame,
                  long_window: int = 252,
                  skip: int = 21) -> pd.DataFrame:
    """12-1 モメンタム: 直近 1 ヶ月を除く過去 12 ヶ月リターン。

    prices: index=日付, columns=銘柄 の終値パネル
    """
    return prices.shift(skip) / prices.shift(long_window) - 1


def short_term_reversal(prices: pd.DataFrame, window: int = 21) -> pd.DataFrame:
    """短期リバーサル: 直近 1 ヶ月リターンの符号反転"""
    return -(prices / prices.shift(window) - 1)


SIGNALS = {
    "momentum_12_1": momentum_12_1,
    "short_term_reversal": short_term_reversal,
}


# ---------------------------------------------------------------------------
# Rank IC 評価
# ---------------------------------------------------------------------------
def forward_returns(prices: pd.DataFrame, horizon: int = 21) -> pd.DataFrame:
    """t 時点から horizon 先までのリターン (t に整列)"""
    return prices.shift(-horizon) / prices - 1


def rank_ic_series(signal: pd.DataFrame,
                   fwd_ret: pd.DataFrame,
                   min_names: int = 10,
                   step: int | None = None) -> pd.Series:
    """各時点の Spearman Rank IC。

    step を horizon と同じにすると非重複サンプリングになり、
    t 統計量の系列相関バイアスを避けられる (推奨)。
    """
    idx = signal.index
    if step:
        idx = idx[::step]
    out = {}
    for t in idx:
        s = signal.loc[t]
        f = fwd_ret.loc[t] if t in fwd_ret.index else None
        if f is None:
            continue
        mask = s.notna() & f.notna()
        if mask.sum() < min_names:
            continue
        ic, _ = stats.spearmanr(s[mask], f[mask])
        out[t] = ic
    return pd.Series(out, dtype=float)


def newey_west_tstat(x: pd.Series, lags: int | None = None) -> float:
    """平均の t 統計量 (Newey-West HAC 標準誤差)"""
    v = x.dropna().to_numpy(dtype=float)
    n = len(v)
    if n < 5:
        return float("nan")
    if lags is None:
        lags = int(np.floor(4 * (n / 100) ** (2 / 9)))
    e = v - v.mean()
    s = float(np.dot(e, e)) / n
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        s += 2 * w * float(np.dot(e[l:], e[:-l])) / n
    se = np.sqrt(s / n)
    return float(v.mean() / se) if se > 0 else float("nan")


def evaluate_signal(prices: pd.DataFrame,
                    signal_fn,
                    horizon: int = 21,
                    non_overlapping: bool = True) -> dict:
    """シグナルの Rank IC 統計を返す。"""
    sig = signal_fn(prices)
    fwd = forward_returns(prices, horizon)
    step = horizon if non_overlapping else None
    ics = rank_ic_series(sig, fwd, step=step)
    t = newey_west_tstat(ics)
    return {
        "mean_ic": float(ics.mean()),
        "ic_std": float(ics.std()),
        "ic_ir": float(ics.mean() / ics.std()) if ics.std() > 0 else float("nan"),
        "t_stat_nw": t,
        "significant_5pct": bool(abs(t) > 1.96),
        "n_periods": int(ics.notna().sum()),
        "horizon_days": horizon,
        "pct_positive": float((ics > 0).mean()),
    }


# ---------------------------------------------------------------------------
# クインタイル・ロングショート (IC をリターンに変換した場合の確認用)
# ---------------------------------------------------------------------------
def quintile_long_short(prices: pd.DataFrame, signal: pd.DataFrame,
                        horizon: int = 21, n_q: int = 5) -> pd.Series:
    """シグナル上位クインタイル買い・下位売りの期間リターン系列 (非重複)"""
    fwd = forward_returns(prices, horizon)
    out = {}
    for t in signal.index[::horizon]:
        if t not in fwd.index:
            continue
        s, f = signal.loc[t], fwd.loc[t]
        mask = s.notna() & f.notna()
        if mask.sum() < n_q * 2:
            continue
        ranks = s[mask].rank(pct=True)
        long = f[mask][ranks > 1 - 1 / n_q].mean()
        short = f[mask][ranks <= 1 / n_q].mean()
        out[t] = long - short
    return pd.Series(out, dtype=float)


# ---------------------------------------------------------------------------
# ユニバース取得 (実データ実行用。CI / ローカルで使用)
# ---------------------------------------------------------------------------
DEFAULT_UNIVERSE = [
    # S&P500 大型株のサンプル 40 銘柄 (セクター分散)。本格運用では
    # 指数構成銘柄の point-in-time リストに置き換えること (生存バイアス注意)。
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "BRK-B", "JPM", "V", "MA",
    "UNH", "JNJ", "PFE", "MRK", "ABBV", "XOM", "CVX", "COP", "PG", "KO",
    "PEP", "WMT", "COST", "HD", "MCD", "DIS", "NFLX", "CRM", "ORCL", "INTC",
    "AMD", "QCOM", "TXN", "GE", "CAT", "BA", "UPS", "GS", "MS", "BAC",
]


def fetch_universe(tickers: list[str] | None = None,
                   period: str = "5y") -> pd.DataFrame:
    """yfinance からユニバースの調整後終値パネルを取得する。

    注意: 現在の構成銘柄を過去に遡って使うため生存バイアスがある。
    Rank IC の楽観バイアス要因として結果に明記すること。
    """
    import yfinance as yf
    tickers = tickers or DEFAULT_UNIVERSE
    data = yf.download(tickers, period=period, auto_adjust=True,
                       progress=False)["Close"]
    return data.dropna(how="all")
