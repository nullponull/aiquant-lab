"""BaselineAgent: ルールベースのコントロール群（LLM 不使用）"""

from .base import Agent, Decision, MarketContext, Action, Timer


class BaselineAgent(Agent):
    """シンプルなモメンタムルール

    LLM を一切使わない。比較対象として「LLM の追加価値」を測るための基準点。
    """

    def __init__(self, lookback: int = 20, threshold: float = 0.0, name: str = "Baseline-Momentum"):
        super().__init__(name)
        self.lookback = lookback
        self.threshold = threshold

    def decide(self, ctx: MarketContext) -> Decision:
        with Timer() as t:
            prices = ctx.recent_prices
            if len(prices) < 2:
                return self._neutral(t.elapsed if hasattr(t, "elapsed") else 0)

            # 単純なモメンタム: 直近リターン
            lookback = min(self.lookback, len(prices) - 1)
            ret = (prices[-1] - prices[-lookback]) / prices[-lookback]

            if ret > self.threshold:
                action = Action.LONG
            elif ret < -self.threshold:
                action = Action.SHORT
            else:
                action = Action.NEUTRAL

            confidence = min(0.9, 0.5 + abs(ret) * 5)

        return Decision(
            action=action,
            confidence=confidence,
            reasoning=f"Pure momentum rule: {lookback}d return = {ret:.2%}",
            tokens_used=0,
            api_calls=0,
            elapsed_seconds=t.elapsed,
            metadata={"agent_type": "baseline", "return": ret},
        )

    def _neutral(self, elapsed: float) -> Decision:
        return Decision(
            action=Action.NEUTRAL,
            confidence=0.3,
            reasoning="Insufficient data",
            tokens_used=0,
            api_calls=0,
            elapsed_seconds=elapsed,
            metadata={"agent_type": "baseline"},
        )
