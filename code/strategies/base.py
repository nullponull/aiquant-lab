"""戦略バックテストの共通基盤 (Ep7 以降で使用)

v2 での主な修正点 (旧実装の問題と対応):

1. 約定タイミングの不整合を解消
   旧実装は「翌日始値で約定する想定」とコメントしつつ、実際は
   ``signals.shift(1) × close-to-close リターン`` で、シグナルを観測した
   その終値で約定できる前提 (楽観的) になっていた。
   v2 では execution モードを明示する:

   - ``"next_open"`` (デフォルト・推奨):
     day t の終値でシグナル確定 → day t+1 の始値で約定。
     P&L は open-to-open リターンで計測する。最も現実に近い。
   - ``"next_close"`` (旧互換):
     旧実装と同一 (shift(1) × close-to-close)。過去記事の数値を
     再現したい場合のみ使用する。

2. スリッページを追加 (``slippage``, 片道, デフォルト 0.05%)
   手数料 (``commission``) と合わせてポジション変化量に比例して控除。

3. トレード統計をトレード単位で計算
   旧実装はポジション変化回数を「トレード数」とし (往復で 2 カウント)、
   勝率も「ポジション保有日のうち日次リターンが正の日の割合」という
   日次ベースの近似だった。v2 はポジションの連続保有区間を 1 トレードと
   して区切り、トレード単位のリターンから勝率を計算する。

4. 短期間評価での年率換算の濫用を抑止
   30 営業日程度のリターンを年率換算すると極端な値になる
   (例: 旧 results/004 で Buy-and-Hold の Sharpe 6.1)。
   ``MIN_DAYS_FOR_ANNUALIZATION`` (デフォルト 126 営業日) 未満の場合、
   annualized_return / sharpe は計算するが ``annualization_reliable=False``
   を立て、save_results にも警告を残す。

5. データ取得の再現性
   ``fetch_spy_data`` は取得結果を ``data/cache/`` に CSV スナップショット
   として保存し、同一日の再実行ではキャッシュを読む。過去の実験を
   再現する場合は ``snapshot`` 引数でスナップショットファイルを指定する。

注意: 本コードは研究目的であり、投資判断・収益を保証するものではない。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


COMMISSION = 0.0005          # 片道 0.05%
SLIPPAGE = 0.0005            # 片道 0.05% (執行スリッページの保守的な仮定)
ANNUAL_TRADING_DAYS = 252
MIN_DAYS_FOR_ANNUALIZATION = 126  # これ未満の期間では年率換算を信頼しない

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "data" / "cache"


# ---------------------------------------------------------------------------
# 結果コンテナ
# ---------------------------------------------------------------------------
@dataclass
class Trade:
    """1 トレード (同一方向ポジションの連続保有区間)"""
    direction: int            # +1 long / -1 short
    entry_date: str
    exit_date: str
    n_days: int
    gross_return: float       # コスト控除前
    net_return: float         # コスト控除後

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategyResult:
    name: str
    n_days: int
    n_trades: int
    total_return: float            # 期間全体の累積リターン (コスト控除後)
    annualized_return: float
    annualization_reliable: bool   # n_days >= MIN_DAYS_FOR_ANNUALIZATION
    sharpe: float
    max_drawdown: float
    win_rate: float | None         # トレード単位の勝率
    avg_trade_return: float | None
    turnover: float                # 期間中のポジション変化量合計 (片道換算)
    total_cost: float              # コストによる累積リターン控除分 (概算)
    final_equity_jpy: int
    survival: str                  # alive / wounded / dead
    execution: str                 # next_open / next_close
    trades: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# トレード分割ユーティリティ
# ---------------------------------------------------------------------------
def segment_trades(pos: pd.Series, ret_after_cost: pd.Series,
                   ret_before_cost: pd.Series) -> list[Trade]:
    """ポジション系列を連続保有区間 (トレード) に分割する。

    pos が 0 → 非0 になった点をエントリー、非0 → 0 / 符号反転を
    エグジットとみなす。符号反転は同時に新トレードのエントリー。
    """
    trades: list[Trade] = []
    cur_dir = 0
    seg_net: list[float] = []
    seg_gross: list[float] = []
    seg_dates: list = []

    def close_segment():
        nonlocal seg_net, seg_gross, seg_dates, cur_dir
        if cur_dir != 0 and seg_dates:
            net = float(np.prod([1 + r for r in seg_net]) - 1)
            gross = float(np.prod([1 + r for r in seg_gross]) - 1)
            trades.append(Trade(
                direction=cur_dir,
                entry_date=str(pd.Timestamp(seg_dates[0]).date()),
                exit_date=str(pd.Timestamp(seg_dates[-1]).date()),
                n_days=len(seg_dates),
                gross_return=gross,
                net_return=net,
            ))
        seg_net, seg_gross, seg_dates = [], [], []

    for dt in pos.index:
        p = int(pos.loc[dt])
        if p != cur_dir:
            close_segment()
            cur_dir = p
        if cur_dir != 0:
            seg_net.append(float(ret_after_cost.loc[dt]))
            seg_gross.append(float(ret_before_cost.loc[dt]))
            seg_dates.append(dt)
    close_segment()
    return trades


# ---------------------------------------------------------------------------
# バックテスト本体
# ---------------------------------------------------------------------------
def _position_and_returns(df: pd.DataFrame, signals: pd.Series,
                          execution: str) -> tuple[pd.Series, pd.Series]:
    """execution モードに応じた (ポジション, 市場リターン) を返す共通処理"""
    signals = signals.reindex(df.index).fillna(0).clip(-1, 1)
    if execution == "next_open":
        if "open" not in df.columns:
            raise ValueError("execution='next_open' には 'open' カラムが必要です")
        # day t 終値でシグナル確定 → day t+1 始値で約定。
        # ret(t) = open(t)/open(t-1)-1 の区間 [open(t-1), open(t)] を
        # 保有するのは「t-1 の始値で約定済み」のポジション = signal(t-2)。
        ret = df["open"].pct_change().fillna(0)
        pos = signals.shift(2).fillna(0)
    elif execution == "next_close":
        # 旧互換: day t 終値でシグナル確定 → 同じ day t 終値で約定できた
        # とみなす楽観的モデル (シグナル生成に使った価格で約定)。
        ret = df["close"].pct_change().fillna(0)
        pos = signals.shift(1).fillna(0)
    else:
        raise ValueError(f"unknown execution mode: {execution}")
    return pos.clip(-1, 1), ret


def equity_curve(df: pd.DataFrame, signals: pd.Series,
                 execution: str = "next_open",
                 commission: float = COMMISSION,
                 slippage: float = SLIPPAGE) -> pd.Series:
    """コスト控除後のエクイティカーブ (初期値 1.0) を返す"""
    pos, ret = _position_and_returns(df, signals, execution)
    per_side_cost = commission + slippage
    trade_changes = pos.diff().abs().fillna(pos.abs())
    strat_ret = pos * ret - trade_changes * per_side_cost
    return (1 + strat_ret).cumprod()


def backtest(name: str,
             df: pd.DataFrame,
             signals: pd.Series,
             initial_jpy: int = 1_000_000,
             execution: str = "next_open",
             commission: float = COMMISSION,
             slippage: float = SLIPPAGE,
             keep_trades: bool = False) -> StrategyResult:
    """1 戦略のバックテスト。

    Args:
        df: 'close' (next_open の場合は 'open' も) を含む価格 DataFrame
        signals: -1/0/+1 のポジションシグナル (day t の終値時点で確定)
        initial_jpy: 開始資金
        execution: "next_open" (推奨) / "next_close" (旧互換)
        commission: 片道手数料率
        slippage: 片道スリッページ率
        keep_trades: True で StrategyResult.trades に明細を残す
    """
    pos, ret = _position_and_returns(df, signals, execution)
    strat_ret_gross = pos * ret

    # ポジション変化 1 単位あたり (commission + slippage) を控除
    per_side_cost = commission + slippage
    trade_changes = pos.diff().abs().fillna(pos.abs())  # 初日のエントリーもカウント
    cost = trade_changes * per_side_cost
    strat_ret = strat_ret_gross - cost

    equity = (1 + strat_ret).cumprod()
    total_return = float(equity.iloc[-1] - 1.0) if len(equity) else 0.0

    n_days = len(equity)
    annualization_reliable = n_days >= MIN_DAYS_FOR_ANNUALIZATION
    if n_days > 0:
        annualized = (1 + total_return) ** (ANNUAL_TRADING_DAYS / n_days) - 1
    else:
        annualized = 0.0

    mean_ret = strat_ret.mean()
    std_ret = strat_ret.std()
    sharpe = float(mean_ret / std_ret * math.sqrt(ANNUAL_TRADING_DAYS)) if std_ret > 0 else 0.0

    cummax = equity.cummax()
    dd = equity / cummax - 1.0
    max_dd = float(dd.min()) if len(dd) else 0.0

    trades = segment_trades(pos, strat_ret, strat_ret_gross)
    n_trades = len(trades)
    if n_trades > 0:
        trade_rets = [t.net_return for t in trades]
        win_rate = float(np.mean([r > 0 for r in trade_rets]))
        avg_trade_return = float(np.mean(trade_rets))
    else:
        win_rate = None
        avg_trade_return = None

    turnover = float(trade_changes.sum())
    total_cost = float(cost.sum())

    final_equity = int(initial_jpy * float(equity.iloc[-1])) if len(equity) else initial_jpy

    if total_return >= 0:
        survival = "alive"
    elif total_return >= -0.10:
        survival = "wounded"
    else:
        survival = "dead"

    return StrategyResult(
        name=name,
        n_days=n_days,
        n_trades=n_trades,
        total_return=float(total_return),
        annualized_return=float(annualized),
        annualization_reliable=annualization_reliable,
        sharpe=sharpe,
        max_drawdown=max_dd,
        win_rate=win_rate,
        avg_trade_return=avg_trade_return,
        turnover=turnover,
        total_cost=total_cost,
        final_equity_jpy=final_equity,
        survival=survival,
        execution=execution,
        trades=[t.to_dict() for t in trades] if keep_trades else [],
    )


# ---------------------------------------------------------------------------
# データ取得 (スナップショット保存つき)
# ---------------------------------------------------------------------------
def fetch_spy_data(period_days: int = 60,
                   snapshot: str | Path | None = None,
                   cache: bool = True) -> pd.DataFrame:
    """SPY の直近データを取得する。

    - ``snapshot`` を指定するとそのスナップショット CSV を読む (再現用)。
    - 指定がなければ yfinance から取得し、``data/cache/spy_{today}_{period}d.csv``
      に保存する。同一日に再実行した場合はキャッシュを読む (決定性のため)。
    """
    if snapshot is not None:
        df = pd.read_csv(snapshot, index_col=0, parse_dates=True)
        return df[["open", "high", "low", "close", "volume"]]

    cache_path = CACHE_DIR / f"spy_{date.today().isoformat()}_{period_days}d.csv"
    if cache and cache_path.exists():
        df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        return df[["open", "high", "low", "close", "volume"]]

    import yfinance as yf
    ticker = yf.Ticker("SPY")
    df = ticker.history(period=f"{period_days}d", auto_adjust=True)
    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]]
    if cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_path)
    return df


# ---------------------------------------------------------------------------
# 結果保存
# ---------------------------------------------------------------------------
def save_results(results: list[StrategyResult], out_dir: Path,
                 experiment: str = "10 戦略並列バックテスト",
                 symbol: str = "SPY") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    n_days = results[0].n_days if results else 0
    summary = {
        "config": {
            "experiment": experiment,
            "symbol": symbol,
            "initial_capital_jpy": 1_000_000,
            "commission": COMMISSION,
            "slippage": SLIPPAGE,
            "execution": results[0].execution if results else None,
            "engine_version": 2,
        },
        "warnings": ([
            f"評価期間が {n_days} 営業日と短いため、annualized_return / sharpe は"
            f"統計的に信頼できません (最低 {MIN_DAYS_FOR_ANNUALIZATION} 営業日を推奨)。"
        ] if results and not results[0].annualization_reliable else []),
        "strategies": [r.to_dict() for r in results],
        "summary": {
            "alive": sum(1 for r in results if r.survival == "alive"),
            "wounded": sum(1 for r in results if r.survival == "wounded"),
            "dead": sum(1 for r in results if r.survival == "dead"),
        },
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
