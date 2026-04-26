"""Episode 2 実験: LLM 議論型 vs Evaluator 型 の比較

検証対象:
- Solo (1体)
- Debate-3 (3体, 1ラウンド)
- Debate-5 (5体, 1ラウンド)
- Debate-3x2 (3体, 2ラウンド)
- Debate-10 (10体, 1ラウンド)
- Evaluator (Generator/Evaluator 分離)
- Baseline (ルールベース、コントロール)

各エージェントを N 個の市場イベントに対して走らせ、
- 判断の正解率（実際のリターンと方向性が一致したか）
- API 呼び出し数
- 消費トークン数
- 推定 API コスト
- 実行時間

を測定する。

使い方:
  # API キーなし（モックで動作確認）
  uv run python code/experiments/run_episode2.py --mock

  # API キーあり（実 LLM で実験）
  export ANTHROPIC_API_KEY=sk-ant-...
  uv run python code/experiments/run_episode2.py --n-events 20
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

import yfinance as yf
import pandas as pd
import numpy as np

# パス調整: code ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import SoloAgent, DebateAgent, EvaluatorAgent, BaselineAgent
from agents.base import MarketContext, Action
from agents.llm_client import MockLLMClient, get_default_client


RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "002"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# Claude Haiku 4.5 の価格 (2026年4月時点の参考値)
# Input:  $1.0 / 1M tokens
# Output: $5.0 / 1M tokens
COST_PER_1M_INPUT = 1.0
COST_PER_1M_OUTPUT = 5.0
# トークン内訳が分からないので、平均 70% input / 30% output と仮定
AVG_COST_PER_1K_TOKENS = (
    0.7 * COST_PER_1M_INPUT + 0.3 * COST_PER_1M_OUTPUT
) / 1000


def load_events(symbol: str = "SPY", n_events: int = 30, start: str = "2020-01-01"):
    """過去の市場イベントをサンプリング

    ボラティリティが高かった日を選んで「興味深いイベント」とする。
    """
    df = yf.Ticker(symbol).history(start=start, auto_adjust=True)
    df["return"] = df["Close"].pct_change()
    df["abs_return"] = df["return"].abs()

    # ボラの高い日を上位から N 日抽出
    high_vol_days = df.nlargest(n_events * 3, "abs_return")
    sample = high_vol_days.sample(n=n_events, random_state=42).sort_index()

    events = []
    for date, row in sample.iterrows():
        idx = df.index.get_loc(date)
        if idx < 20 or idx + 5 >= len(df):
            continue

        prices = df["Close"].iloc[idx-20:idx].tolist()
        future_5d_return = (df["Close"].iloc[idx+5] - df["Close"].iloc[idx]) / df["Close"].iloc[idx]

        events.append({
            "symbol": symbol,
            "date": date.strftime("%Y-%m-%d"),
            "recent_prices": prices,
            "future_5d_return": float(future_5d_return),
            "future_direction": "LONG" if future_5d_return > 0.005 else ("SHORT" if future_5d_return < -0.005 else "NEUTRAL"),
            "current_price": float(df["Close"].iloc[idx]),
            "current_return": float(row["return"]),
        })

    return events


def make_context(event: dict) -> MarketContext:
    """イベントから MarketContext を生成

    ニュース見出しは合成（実装は後で alternative data に置き換え）
    """
    direction = "上昇" if event["current_return"] > 0 else "下落"
    return MarketContext(
        symbol=event["symbol"],
        date=event["date"],
        recent_prices=event["recent_prices"],
        news_headlines=[
            f"{event['symbol']} moves {event['current_return']*100:.1f}% on heavy volume",
            f"Market volatility elevated on {event['date']}",
            f"Analysts watch for follow-through after recent {direction} action",
        ],
        macro_indicators={},
        horizon_days=5,
    )


def evaluate_decision(decision_action: str, true_direction: str) -> dict:
    """判断の正誤を評価"""
    # 完全一致
    exact_match = decision_action == true_direction

    # 方向性一致（NEUTRAL を除外して LONG/SHORT のみで評価）
    if decision_action in ("LONG", "SHORT") and true_direction in ("LONG", "SHORT"):
        directional_match = decision_action == true_direction
    else:
        directional_match = None  # NEUTRAL を含むので評価対象外

    return {
        "exact_match": exact_match,
        "directional_match": directional_match,
    }


def run_single_agent(agent, events):
    """1 エージェントを全イベントに対して走らせる"""
    results = []
    for i, event in enumerate(events):
        ctx = make_context(event)
        decision = agent.decide(ctx)
        eval_result = evaluate_decision(decision.action.value, event["future_direction"])

        # 仮定的リターン: アクションが LONG なら +future_5d_return、SHORT なら -future_5d_return
        if decision.action == Action.LONG:
            hyp_return = event["future_5d_return"]
        elif decision.action == Action.SHORT:
            hyp_return = -event["future_5d_return"]
        else:
            hyp_return = 0.0

        results.append({
            "event_idx": i,
            "date": event["date"],
            "decision": decision.action.value,
            "confidence": decision.confidence,
            "true_direction": event["future_direction"],
            "future_5d_return": event["future_5d_return"],
            "hypothetical_return": hyp_return,
            "tokens": decision.tokens_used,
            "api_calls": decision.api_calls,
            "elapsed": decision.elapsed_seconds,
            "exact_match": eval_result["exact_match"],
            "directional_match": eval_result["directional_match"],
        })

    return results


def summarize(name: str, results: list[dict]) -> dict:
    df = pd.DataFrame(results)

    directional_results = df[df["directional_match"].notna()]

    return {
        "agent": name,
        "n_events": len(df),
        "exact_accuracy": float(df["exact_match"].mean()),
        "directional_accuracy": float(directional_results["directional_match"].mean()) if len(directional_results) > 0 else None,
        "directional_n": len(directional_results),
        "avg_hypothetical_return": float(df["hypothetical_return"].mean()),
        "total_hypothetical_return": float(df["hypothetical_return"].sum()),
        "avg_tokens_per_decision": float(df["tokens"].mean()),
        "total_tokens": int(df["tokens"].sum()),
        "total_api_calls": int(df["api_calls"].sum()),
        "estimated_cost_usd": float(df["tokens"].sum() * AVG_COST_PER_1K_TOKENS),
        "avg_elapsed_seconds": float(df["elapsed"].mean()),
        "long_rate": float((df["decision"] == "LONG").mean()),
        "short_rate": float((df["decision"] == "SHORT").mean()),
        "neutral_rate": float((df["decision"] == "NEUTRAL").mean()),
        "avg_confidence": float(df["confidence"].mean()),
    }


def cost_per_correct_decision(summary: dict) -> float:
    """正解1判断あたりのコスト"""
    if summary["directional_accuracy"] is None or summary["directional_accuracy"] == 0:
        return float("inf")
    correct_count = summary["directional_accuracy"] * summary["directional_n"]
    if correct_count == 0:
        return float("inf")
    return summary["estimated_cost_usd"] / correct_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="モックLLMで実行")
    parser.add_argument("--cli", action="store_true", help="Claude CLI を試す（投資分析を拒否される可能性あり）")
    parser.add_argument("--n-events", type=int, default=20, help="検証イベント数")
    parser.add_argument("--symbol", type=str, default="SPY")
    args = parser.parse_args()

    client = get_default_client(use_mock=args.mock, use_cli=args.cli)
    print(f"Client: {client.__class__.__name__}")

    print(f"\n=== イベント取得 (n={args.n_events}, symbol={args.symbol}) ===")
    events = load_events(symbol=args.symbol, n_events=args.n_events)
    print(f"取得イベント数: {len(events)}")

    # 真の方向の分布
    true_dir_counts = pd.Series([e["future_direction"] for e in events]).value_counts()
    print(f"True direction distribution: {dict(true_dir_counts)}")

    # エージェント定義
    agents_to_test = [
        BaselineAgent(),
        SoloAgent(client=client),
        DebateAgent(n_agents=3, n_rounds=1, client=client, name="Debate-3"),
        DebateAgent(n_agents=5, n_rounds=1, client=client, name="Debate-5"),
        DebateAgent(n_agents=3, n_rounds=2, client=client, name="Debate-3x2"),
        DebateAgent(n_agents=10, n_rounds=1, client=client, name="Debate-10"),
        EvaluatorAgent(k_hypotheses=5, client=client),
    ]

    all_results = {}
    summaries = []

    for agent in agents_to_test:
        print(f"\n=== {agent.name} を実行中 ===")
        results = run_single_agent(agent, events)
        summary = summarize(agent.name, results)
        summary["cost_per_correct"] = cost_per_correct_decision(summary)
        summaries.append(summary)
        all_results[agent.name] = results

        print(f"  方向正解率: {summary['directional_accuracy']:.1%}" if summary['directional_accuracy'] else "  方向正解率: N/A")
        print(f"  累積仮想リターン: {summary['total_hypothetical_return']:.2%}")
        print(f"  総トークン: {summary['total_tokens']:,}")
        print(f"  推定コスト: ${summary['estimated_cost_usd']:.4f}")
        print(f"  正解1判断あたりコスト: ${summary['cost_per_correct']:.5f}")

    # 比較表
    print("\n=== 比較サマリー ===")
    df_sum = pd.DataFrame(summaries)
    cols = ["agent", "directional_accuracy", "total_hypothetical_return",
            "total_tokens", "estimated_cost_usd", "cost_per_correct"]
    print(df_sum[cols].to_string(index=False))

    # 保存
    output = {
        "config": {
            "n_events": args.n_events,
            "symbol": args.symbol,
            "client": client.__class__.__name__,
            "timestamp": datetime.now().isoformat(),
        },
        "summaries": summaries,
        "events": events,
    }

    with open(RESULTS_DIR / "summary.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    # 詳細結果も保存
    for agent_name, results in all_results.items():
        safe_name = agent_name.replace("/", "_").replace(" ", "_")
        pd.DataFrame(results).to_csv(RESULTS_DIR / f"detail_{safe_name}.csv", index=False)

    print(f"\n結果保存: {RESULTS_DIR}")
    return output


if __name__ == "__main__":
    main()
