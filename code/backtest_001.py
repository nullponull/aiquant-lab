"""
記事001: 「3週間で+4%勝てた」AI自動売買戦略の10年バックテスト

匿名化のため、対象ツイートの戦略を一般化:
- 70%: 配当貴族（NOBL ETFをプロキシとして使用）
- 30%: 中期成長株（SPYを母集団とし、トレーリング8%損切/20%利確）

期待値計算の検証も同時に実施。
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import json
from pathlib import Path

RESULTS_DIR = Path(__file__).parent.parent / "results" / "001"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def fetch_data(start="2014-01-01", end="2024-12-31"):
    """配当貴族(NOBL)、S&P500(SPY)、グロース(QQQ)を取得"""
    tickers = ["NOBL", "SPY", "QQQ"]
    data = {}
    for t in tickers:
        df = yf.Ticker(t).history(start=start, end=end, auto_adjust=True)
        data[t] = df["Close"]
    return pd.DataFrame(data).dropna()


def simulate_strategy(prices: pd.DataFrame, initial_capital=1_000_000):
    """
    戦略シミュレーション:
    - 70%: NOBL（配当貴族）にバイアンドホールド
    - 30%: グロース部分（QQQ）に -8%/+20% ルールで運用
       - 損切り or 利確時に再エントリー（次営業日）
    """
    cap = initial_capital
    div_alloc = cap * 0.70
    growth_alloc = cap * 0.30

    # 配当貴族部分: NOBLバイアンドホールド
    nobl_units = div_alloc / prices["NOBL"].iloc[0]

    # 中期成長部分: ルールベース取引
    growth_cash = growth_alloc
    growth_position = None  # {"entry_price": ..., "units": ...}
    growth_trades = []

    daily_value = []
    for date, row in prices.iterrows():
        nobl_value = nobl_units * row["NOBL"]

        # 中期成長部分のロジック
        if growth_position is None:
            # 新規エントリー
            entry_price = row["QQQ"]
            units = growth_cash / entry_price
            growth_position = {
                "entry_price": entry_price,
                "units": units,
                "entry_date": date,
            }
            growth_value = growth_cash
        else:
            current_price = row["QQQ"]
            ret = (current_price - growth_position["entry_price"]) / growth_position["entry_price"]

            if ret <= -0.08 or ret >= 0.20:
                # 損切り or 利確
                exit_value = growth_position["units"] * current_price
                growth_trades.append({
                    "entry_date": str(growth_position["entry_date"].date()),
                    "exit_date": str(date.date()),
                    "entry_price": growth_position["entry_price"],
                    "exit_price": current_price,
                    "return": ret,
                    "result": "TP" if ret >= 0.20 else "SL",
                })
                growth_cash = exit_value
                # 翌日エントリー（同日にも再エントリーする簡略実装）
                new_entry = current_price
                units = growth_cash / new_entry
                growth_position = {
                    "entry_price": new_entry,
                    "units": units,
                    "entry_date": date,
                }
                growth_value = growth_cash
            else:
                growth_value = growth_position["units"] * current_price

        total = nobl_value + growth_value
        daily_value.append({"date": date, "total": total, "nobl": nobl_value, "growth": growth_value})

    return pd.DataFrame(daily_value).set_index("date"), growth_trades


def yearly_returns(equity: pd.Series) -> pd.Series:
    yearly = equity.resample("YE").last()
    return yearly.pct_change().dropna()


def benchmark_spy(prices: pd.DataFrame, initial=1_000_000):
    units = initial / prices["SPY"].iloc[0]
    return prices["SPY"] * units


def calc_metrics(equity: pd.Series, label: str) -> dict:
    rets = equity.pct_change().dropna()
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (252 / len(equity)) - 1
    sharpe = (rets.mean() / rets.std()) * np.sqrt(252) if rets.std() > 0 else 0
    cummax = equity.cummax()
    dd = (equity - cummax) / cummax
    max_dd = dd.min()
    return {
        "label": label,
        "final_value": float(equity.iloc[-1]),
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "cagr": float(cagr),
        "sharpe": float(sharpe),
        "max_drawdown": float(max_dd),
    }


def three_week_simulation(prices: pd.DataFrame, n_periods=200):
    """
    3週間（15営業日）リターンの分布を取り、
    +4%以上を達成する確率を測る = ノイズで起きる確率
    """
    rets = prices["SPY"].pct_change().dropna()
    rolling_3w = rets.rolling(15).apply(lambda x: (1 + x).prod() - 1).dropna()
    pct_above_4 = (rolling_3w >= 0.04).mean()
    return {
        "mean_3w_return": float(rolling_3w.mean()),
        "std_3w_return": float(rolling_3w.std()),
        "pct_above_4pct": float(pct_above_4),
        "median": float(rolling_3w.median()),
    }


def main():
    print("=== データ取得中 ===")
    prices = fetch_data()
    print(f"期間: {prices.index[0].date()} 〜 {prices.index[-1].date()}")
    print(f"営業日数: {len(prices)}")

    print("\n=== 戦略シミュレーション ===")
    equity, trades = simulate_strategy(prices)
    strategy_metrics = calc_metrics(equity["total"], "ツイート戦略（70/30）")

    print("\n=== ベンチマーク（SPYバイアンドホールド）===")
    spy_equity = benchmark_spy(prices)
    spy_metrics = calc_metrics(spy_equity, "SPYバイアンドホールド")

    print("\n=== NOBL（配当貴族のみ）===")
    nobl_equity = (1_000_000 / prices["NOBL"].iloc[0]) * prices["NOBL"]
    nobl_metrics = calc_metrics(nobl_equity, "NOBL単独")

    print("\n=== 年次リターン比較 ===")
    sty = yearly_returns(equity["total"])
    spy_y = yearly_returns(spy_equity)
    yearly_df = pd.DataFrame({
        "戦略": sty,
        "SPY": spy_y,
    })
    print(yearly_df.to_string())

    print("\n=== 3週間ノイズ分布 ===")
    noise = three_week_simulation(prices)
    print(json.dumps(noise, indent=2, ensure_ascii=False))

    print("\n=== 取引統計 ===")
    if trades:
        tdf = pd.DataFrame(trades)
        print(f"総取引数: {len(tdf)}")
        print(f"利確数: {(tdf['result']=='TP').sum()}")
        print(f"損切数: {(tdf['result']=='SL').sum()}")
        print(f"勝率: {(tdf['result']=='TP').mean()*100:.1f}%")
        print(f"平均リターン: {tdf['return'].mean()*100:.2f}%")
        # 期待値の実測検証
        wins = tdf[tdf['result']=='TP']['return'].mean()
        losses = tdf[tdf['result']=='SL']['return'].mean()
        win_rate = (tdf['result']=='TP').mean()
        ev = win_rate * wins + (1 - win_rate) * losses
        print(f"実測EV/取引: {ev*100:.3f}%")
        print(f"理論EV(33% TP/67% SL): {0.33*0.20 + 0.67*-0.08:.3f}")

    # 結果保存
    output = {
        "period": f"{prices.index[0].date()} - {prices.index[-1].date()}",
        "metrics": {
            "strategy": strategy_metrics,
            "spy_benchmark": spy_metrics,
            "nobl_only": nobl_metrics,
        },
        "yearly_returns": yearly_df.to_dict("index"),
        "noise_analysis": noise,
        "trades_summary": {
            "total": len(trades),
            "tp": sum(1 for t in trades if t["result"]=="TP"),
            "sl": sum(1 for t in trades if t["result"]=="SL"),
        } if trades else None,
    }

    # 日付キーを文字列化
    output["yearly_returns"] = {
        str(k.date() if hasattr(k, 'date') else k): v
        for k, v in output["yearly_returns"].items()
    }

    with open(RESULTS_DIR / "metrics.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    equity.to_csv(RESULTS_DIR / "equity_curve.csv")
    if trades:
        pd.DataFrame(trades).to_csv(RESULTS_DIR / "trades.csv", index=False)

    print(f"\n結果保存: {RESULTS_DIR}")
    return output


if __name__ == "__main__":
    main()
