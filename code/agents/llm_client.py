"""LLM API クライアント抽象化

3 つの実装を提供:
1. ClaudeCLIClient: Claude Code CLI subprocess（推奨、API キー不要）
2. AnthropicClient: Anthropic API 直接（高速、API キー必要）
3. MockLLMClient: テスト用モック（API なしで動作確認）
"""

import os
import json
import random
import subprocess
import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_creation_tokens + self.cache_read_tokens


class LLMClient:
    """抽象基底"""

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> LLMResponse:
        raise NotImplementedError


class ClaudeCLIClient(LLMClient):
    """Claude Code CLI subprocess 経由で Claude を呼び出す

    特徴:
    - ANTHROPIC_API_KEY 不要（Claude Code サブスクで動作）
    - プロンプトキャッシュが自動で効く
    - 各呼び出しに ~2 秒のオーバーヘッドあり
    - 大量バッチには不向き（200 回 = 10-20 分）

    使用前に Claude CLI のインストールが必要:
      https://claude.com/code
    """

    def __init__(self, model: str = "haiku", timeout: int = 120):
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude CLI が見つかりません。"
                "https://claude.com/code からインストールしてください。"
            )
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> LLMResponse:
        cmd = [
            "claude",
            "-p", user,
            "--model", self.model,
            "--output-format", "json",
            "--append-system-prompt", system,
            "--no-session-persistence",
            "--disable-slash-commands",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude CLI timeout after {self.timeout}s")

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude CLI failed with code {result.returncode}: "
                f"stderr={result.stderr[:500]}"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Claude CLI output is not valid JSON: {result.stdout[:500]}") from e

        if data.get("is_error"):
            raise RuntimeError(f"Claude CLI returned error: {data.get('result', '')}")

        usage = data.get("usage", {})
        return LLMResponse(
            text=data.get("result", ""),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_creation_tokens=usage.get("cache_creation_input_tokens", 0),
            cost_usd=data.get("total_cost_usd", 0.0),
        )


class AnthropicClient(LLMClient):
    """Anthropic Claude API 直接実装（オプション）

    特徴:
    - 高速、低オーバーヘッド
    - ANTHROPIC_API_KEY が必要
    - pip install anthropic
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic ライブラリが必要です: uv add anthropic"
            )
        self.client = anthropic.Anthropic()
        self.model = model

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> LLMResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return LLMResponse(
            text=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


class MockLLMClient(LLMClient):
    """API なしで動作確認するためのモック

    実装の正しさをテストする目的で使う。
    実験本番では AnthropicClient を使うこと。
    """

    def __init__(self, seed: int = 42, base_token_cost: int = 200):
        self.rng = random.Random(seed)
        self.base_token_cost = base_token_cost

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> LLMResponse:
        # ユーザープロンプトの長さに応じてトークン数を擬似的に設定
        input_tokens = len(system) // 3 + len(user) // 3
        output_tokens = self.rng.randint(self.base_token_cost, self.base_token_cost * 3)

        # プロンプトを判定して応答形式を切り替え
        if "hypothesis generator" in system.lower() or "h1:" in system.lower() or "trading hypotheses" in system.lower():
            # Evaluator 用：仮説リストを返す
            features = ["momentum", "mean_reversion", "volatility_breakout", "news_sentiment", "trend_following"]
            actions = ["LONG", "SHORT", "NEUTRAL"]
            weights = [0.45, 0.25, 0.30]
            text_parts = []
            n = 5
            # システムプロンプトから k を抽出
            import re
            m = re.search(r"generate (\d+)", system.lower())
            if m:
                n = int(m.group(1))
            for i in range(n):
                action = self.rng.choices(actions, weights=weights)[0]
                feature = self.rng.choice(features)
                text_parts.append(
                    f"H{i+1}: {action} | {feature} | "
                    f"Mock rationale based on {feature} signal."
                )
            text = "\n".join(text_parts)
            return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)

        # アクション抽出のためのテキストを生成
        actions = ["LONG", "SHORT", "NEUTRAL"]
        weights = [0.45, 0.25, 0.30]  # LONG bias を再現
        chosen = self.rng.choices(actions, weights=weights)[0]
        confidence = round(self.rng.uniform(0.4, 0.85), 2)

        text = (
            f"Action: {chosen}\n"
            f"Confidence: {confidence}\n"
            f"Reasoning: Based on the price action and news context, "
            f"the asymmetric risk profile suggests a {chosen.lower()} position. "
            f"Recent momentum and macro conditions are factored in."
        )
        return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)


def get_default_client(
    use_mock: bool = False,
    use_cli: bool = False,
) -> LLMClient:
    """デフォルトクライアント取得

    公開リポジトリでは AnthropicClient (API直接) を主用する。
    Claude CLI はローカル開発用のオプション。

    優先順位:
    1. use_mock=True なら MockLLMClient
    2. use_cli=True かつ Claude CLI 利用可能なら ClaudeCLIClient
       (注: Claude Code CLI は投資分析を拒否することが多い。詳細は docs/claude_cli_wall.md)
    3. ANTHROPIC_API_KEY があれば AnthropicClient (推奨)
    4. それ以外は MockLLMClient (フレームワーク動作確認用)
    """
    if use_mock:
        return MockLLMClient()
    if use_cli:
        try:
            return ClaudeCLIClient()
        except RuntimeError:
            print("[警告] Claude CLI が利用できません。API またはモックにフォールバック。")
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicClient()
    print("[警告] ANTHROPIC_API_KEY が未設定のため Mock を使用します")
    print("       実 LLM 実験には API キーを設定してください: https://console.anthropic.com")
    return MockLLMClient()
