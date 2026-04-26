"""SoloAgent: 1 LLM 呼び出しで判断"""

import re
from .base import Agent, Decision, MarketContext, Action, Timer
from .llm_client import LLMClient, get_default_client


SYSTEM_PROMPT = """You are a quantitative analyst. Given market context, decide:
- Action: LONG, SHORT, or NEUTRAL
- Confidence: 0.0 to 1.0
- Reasoning: brief explanation (under 100 words)

Respond exactly in this format:
Action: <LONG|SHORT|NEUTRAL>
Confidence: <0.0-1.0>
Reasoning: <text>
"""


def parse_decision(text: str) -> tuple[Action, float, str]:
    """LLM 応答からアクション・確信度・理由を抽出"""
    action_match = re.search(r"Action:\s*(LONG|SHORT|NEUTRAL)", text, re.IGNORECASE)
    conf_match = re.search(r"Confidence:\s*([0-9.]+)", text)
    reason_match = re.search(r"Reasoning:\s*(.+)", text, re.DOTALL)

    action = Action(action_match.group(1).upper()) if action_match else Action.NEUTRAL
    confidence = float(conf_match.group(1)) if conf_match else 0.5
    confidence = max(0.0, min(1.0, confidence))
    reasoning = reason_match.group(1).strip() if reason_match else text

    return action, confidence, reasoning


class SoloAgent(Agent):
    """1 LLM 呼び出しで即座に判断するエージェント"""

    def __init__(self, name: str = "Solo", client: LLMClient | None = None):
        super().__init__(name)
        self.client = client or get_default_client()

    def decide(self, ctx: MarketContext) -> Decision:
        with Timer() as t:
            response = self.client.complete(
                system=SYSTEM_PROMPT,
                user=ctx.summary(),
                max_tokens=512,
            )

        action, confidence, reasoning = parse_decision(response.text)

        return Decision(
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            tokens_used=response.total_tokens,
            api_calls=1,
            elapsed_seconds=t.elapsed,
            metadata={"agent_type": "solo"},
        )
