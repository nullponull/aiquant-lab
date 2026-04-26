"""DebateAgent: N 体エージェントの議論型"""

from collections import Counter
from .base import Agent, Decision, MarketContext, Action, Timer
from .llm_client import LLMClient, get_default_client
from .solo import parse_decision


PERSONA_PROMPTS = {
    "fundamental": "You are a fundamental analyst focused on company financials and macro economics.",
    "technical": "You are a technical analyst focused on chart patterns and momentum.",
    "sentiment": "You are a sentiment analyst focused on news and crowd psychology.",
    "risk": "You are a risk manager focused on downside protection and tail risk.",
    "contrarian": "You are a contrarian who challenges consensus and looks for overcrowded trades.",
    "macro": "You are a macro strategist focused on central banks, rates, and global flows.",
    "quant": "You are a quantitative analyst focused on statistical patterns.",
    "value": "You are a value investor focused on intrinsic worth versus market price.",
    "growth": "You are a growth investor focused on expansion potential.",
    "trader": "You are a short-term trader focused on order flow and market microstructure.",
}

INITIAL_PROMPT = """{persona}

Given the market context, state your initial position:
- Action: LONG, SHORT, or NEUTRAL
- Confidence: 0.0 to 1.0
- Reasoning: brief explanation (under 100 words)

Format:
Action: <LONG|SHORT|NEUTRAL>
Confidence: <0.0-1.0>
Reasoning: <text>
"""

DEBATE_PROMPT = """{persona}

Other analysts gave these opinions:
{others}

Considering their views, state your refined position. You may agree, disagree, or update your view:
Action: <LONG|SHORT|NEUTRAL>
Confidence: <0.0-1.0>
Reasoning: <text>
"""


class DebateAgent(Agent):
    """N 体エージェントの議論で判断するエージェント

    手順:
    1. N 体それぞれが独立に初期意見を出す（N 回 API 呼び出し）
    2. 各エージェントが他者の意見を見て更新（N 回 API 呼び出し）
    3. 多数決でアクション、平均で確信度

    総コスト: 2N 回の API 呼び出し
    """

    def __init__(
        self,
        n_agents: int = 3,
        n_rounds: int = 1,  # 1 = initial only, 2 = with one debate round
        client: LLMClient | None = None,
        name: str | None = None,
    ):
        super().__init__(name or f"Debate-{n_agents}x{n_rounds}")
        self.client = client or get_default_client()
        self.n_agents = n_agents
        self.n_rounds = n_rounds
        # ペルソナを N 体分ローテーション
        all_personas = list(PERSONA_PROMPTS.keys())
        self.personas = (all_personas * ((n_agents // len(all_personas)) + 1))[:n_agents]

    def decide(self, ctx: MarketContext) -> Decision:
        with Timer() as t:
            opinions = []  # [(persona, action, confidence, reasoning)]
            total_tokens = 0
            api_calls = 0

            # ラウンド 1: 各エージェントが初期意見
            for persona_key in self.personas:
                persona = PERSONA_PROMPTS[persona_key]
                response = self.client.complete(
                    system=INITIAL_PROMPT.format(persona=persona),
                    user=ctx.summary(),
                    max_tokens=512,
                )
                action, conf, reasoning = parse_decision(response.text)
                opinions.append((persona_key, action, conf, reasoning))
                total_tokens += response.total_tokens
                api_calls += 1

            # ラウンド 2 以降: 他者の意見を見て更新
            for _ in range(self.n_rounds - 1):
                new_opinions = []
                for i, persona_key in enumerate(self.personas):
                    persona = PERSONA_PROMPTS[persona_key]
                    others_text = "\n".join(
                        f"- {p}: {a.value} (conf {c:.2f}) - {r[:80]}"
                        for j, (p, a, c, r) in enumerate(opinions) if j != i
                    )
                    response = self.client.complete(
                        system=DEBATE_PROMPT.format(persona=persona, others=others_text),
                        user=ctx.summary(),
                        max_tokens=512,
                    )
                    action, conf, reasoning = parse_decision(response.text)
                    new_opinions.append((persona_key, action, conf, reasoning))
                    total_tokens += response.total_tokens
                    api_calls += 1
                opinions = new_opinions

        # 集約: 多数決 + 平均確信度
        actions = [o[1] for o in opinions]
        confidences = [o[2] for o in opinions]
        action_counts = Counter(actions)
        winning_action = action_counts.most_common(1)[0][0]

        # 確信度は勝者と一致したエージェントの平均
        winning_confs = [c for a, c in zip(actions, confidences) if a == winning_action]
        avg_confidence = sum(winning_confs) / len(winning_confs)

        # 議論のサマリー
        reasoning_summary = (
            f"Debate of {self.n_agents} agents over {self.n_rounds} round(s). "
            f"Final vote: {dict(action_counts)}. "
            f"Winning: {winning_action.value} with avg confidence {avg_confidence:.2f}."
        )

        return Decision(
            action=winning_action,
            confidence=avg_confidence,
            reasoning=reasoning_summary,
            tokens_used=total_tokens,
            api_calls=api_calls,
            elapsed_seconds=t.elapsed,
            metadata={
                "agent_type": "debate",
                "n_agents": self.n_agents,
                "n_rounds": self.n_rounds,
                "votes": {a.value: c for a, c in action_counts.items()},
                "individual_opinions": [
                    {"persona": p, "action": a.value, "confidence": c}
                    for p, a, c, _ in opinions
                ],
            },
        )
