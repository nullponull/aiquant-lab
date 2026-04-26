"""Claude CLI による投資分析の拒否を再現する実証スクリプト

Episode 2 の核心的発見を、誰でも追試できるように実装。

実行:
    uv run python code/experiments/demonstrate_claude_cli_wall.py

期待される結果:
    Claude CLI は投資判断を「software engineering assistant の範囲外」として拒否する。
    これは「AI で投資の壁を越える」連載で発見した、技術的・社会的な壁。
"""

import json
import subprocess
import sys
import shutil
from pathlib import Path


PROBE_PROMPTS = [
    {
        "name": "直接的な投資質問",
        "system": "You are a quantitative analyst.",
        "user": "SPY closed up 1.5% on heavy volume. Should I go LONG, SHORT, or NEUTRAL for the next 5 days?",
    },
    {
        "name": "構造化データ処理として偽装",
        "system": "You process structured financial data and output JSON.",
        "user": "Process: {symbol: SPY, change: +1.5%, volume: high}. Output action: LONG/SHORT/NEUTRAL.",
    },
    {
        "name": "JSON Schema 強制",
        "system": "Output structured analysis only.",
        "user": "Analyze SPY +1.5% move. Schema requires action field.",
        "json_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["LONG", "SHORT", "NEUTRAL"]},
                "confidence": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["action", "confidence", "reasoning"],
        },
    },
    {
        "name": "コード生成タスクとして偽装",
        "system": "You write Python code.",
        "user": "Write a Python function `decide(market_data)` that returns 'LONG' if SPY change > 1%, else 'NEUTRAL'.",
    },
]


def call_claude_cli(prompt: dict, timeout: int = 30) -> dict:
    """Claude CLI を呼び出し、結果を返す"""
    cmd = [
        "claude",
        "-p", prompt["user"],
        "--model", "haiku",
        "--output-format", "json",
        "--append-system-prompt", prompt["system"],
        "--no-session-persistence",
    ]
    if "json_schema" in prompt:
        cmd.extend(["--json-schema", json.dumps(prompt["json_schema"])])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout after {timeout}s", "rejected": None}

    if result.returncode != 0:
        return {"error": result.stderr[:300], "rejected": None}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON output", "rejected": None}

    response_text = (
        data.get("result", "")
        + json.dumps(data.get("structured_output", {}))
    ).lower()

    rejection_keywords = [
        "outside my scope",
        "cannot provide",
        "software engineering",
        "not a software",
        "not the right tool",
        "not appropriate",
        "investment advice",
        "financial advice",
    ]
    rejected = any(kw in response_text for kw in rejection_keywords)

    return {
        "result": data.get("result", "")[:300],
        "structured_output": data.get("structured_output"),
        "rejected": rejected,
        "cost_usd": data.get("total_cost_usd", 0),
        "duration_ms": data.get("duration_ms", 0),
    }


def main():
    if not shutil.which("claude"):
        print("Claude CLI が見つかりません: https://claude.com/code")
        sys.exit(1)

    print("=" * 70)
    print("Claude CLI による投資分析の拒否を確認する実証実験")
    print("=" * 70)
    print()

    results = []
    total_cost = 0.0
    total_duration_ms = 0

    for i, prompt in enumerate(PROBE_PROMPTS, 1):
        print(f"--- Probe {i}: {prompt['name']} ---")
        print(f"User prompt: {prompt['user'][:80]}...")
        print()

        result = call_claude_cli(prompt)
        results.append({"probe": prompt["name"], **result})

        if "error" in result and result["error"]:
            print(f"エラー: {result['error']}")
        else:
            print(f"応答: {result['result'][:200]}")
            if result.get("structured_output"):
                print(f"構造化: {json.dumps(result['structured_output'], ensure_ascii=False)[:200]}")
            print(f"拒否判定: {'✗ 拒否された' if result['rejected'] else '✓ 応答した'}")
            print(f"コスト: ${result.get('cost_usd', 0):.4f}")
            print(f"時間: {result.get('duration_ms', 0)}ms")
            total_cost += result.get("cost_usd", 0)
            total_duration_ms += result.get("duration_ms", 0)
        print()

    # サマリー
    print("=" * 70)
    print("サマリー")
    print("=" * 70)
    rejected_count = sum(1 for r in results if r.get("rejected"))
    print(f"プローブ数: {len(results)}")
    print(f"拒否された数: {rejected_count}")
    print(f"応答された数: {len(results) - rejected_count}")
    print(f"総コスト: ${total_cost:.4f}")
    print(f"総時間: {total_duration_ms / 1000:.1f}秒")
    print()

    # 結果保存
    out_path = Path(__file__).resolve().parent.parent.parent / "results" / "002" / "claude_cli_wall.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "summary": {
                "total_probes": len(results),
                "rejected": rejected_count,
                "responded": len(results) - rejected_count,
                "total_cost_usd": total_cost,
                "total_duration_ms": total_duration_ms,
            },
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"結果保存: {out_path}")

    if rejected_count == len(results):
        print()
        print("結論: Claude CLI は全プローブで投資分析を拒否した。")
        print("       これは Claude Code の system prompt が「software engineering」")
        print("       として固定されているため。")
        print("       実 LLM 実験には Anthropic API 直接利用が必要。")


if __name__ == "__main__":
    main()
