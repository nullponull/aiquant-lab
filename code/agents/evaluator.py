"""EvaluatorAgent: Generator/Evaluator 分離パターン

LLM は仮説生成のみ、評価は数値で行う。
QuantEvolve 系の発想（前回までの議論で議論型より優れると示唆された）。
"""

import re
from .base import Agent, Decision, MarketContext, Action, Timer
from .llm_client import LLMClient, get_default_client


GENERATOR_PROMPT = """You are a hypothesis generator for quantitative trading.

Given the market context, generate {k} distinct trading hypotheses.
Each hypothesis should specify:
- Direction (LONG/SHORT/NEUTRAL)
- Key feature it relies on (e.g., "momentum", "mean_reversion", "news_sentiment", "volatility_breakout")
- Brief rationale (one sentence)

Format:
H1: <LONG|SHORT|NEUTRAL> | <feature> | <rationale>
H2: <LONG|SHORT|NEUTRAL> | <feature> | <rationale>
...

Just generate diverse hypotheses; do not pick one. The numerical evaluator will score them.
"""


def parse_hypotheses(text: str) -> list[dict]:
    """LLM 応答から仮説リストを抽出"""
    pattern = r"H\d+:\s*(LONG|SHORT|NEUTRAL)\s*\|\s*([^|]+?)\s*\|\s*(.+)"
    hypotheses = []
    for line in text.split("\n"):
        m = re.search(pattern, line, re.IGNORECASE)
        if m:
            hypotheses.append({
                "direction": Action(m.group(1).upper()),
                "feature": m.group(2).strip().lower(),
                "rationale": m.group(3).strip(),
            })
    return hypotheses


def numerical_evaluator(hypothesis: dict, ctx: MarketContext) -> float:
    """仮説を数値で評価（LLM 不使用）

    各特徴量について、過去データから計算可能な指標で評価する。
    値は -1.0 (反対) 〜 +1.0 (強い支持)
    """
    prices = ctx.recent_prices
    if len(prices) < 5:
        return 0.0

    feature = hypothesis["feature"]
    direction = hypothesis["direction"]

    # 各特徴量について簡易的な数値スコアを返す
    score = 0.0

    if "momentum" in feature:
        # 直近5日リターン
        ret_5d = (prices[-1] - prices[-5]) / prices[-5]
        score = max(-1, min(1, ret_5d * 20))  # 5%動きで±1

    elif "mean_reversion" in feature or "reversion" in feature:
        # 平均からの乖離（z-score）
        mean = sum(prices) / len(prices)
        std = (sum((p - mean) ** 2 for p in prices) / len(prices)) ** 0.5
        if std > 0:
            z = (prices[-1] - mean) / std
            score = max(-1, min(1, -z / 2))  # 高すぎたらSHORT支持

    elif "volatility" in feature or "breakout" in feature:
        # 直近ボラティリティ
        rets = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        if rets:
            vol = (sum(r ** 2 for r in rets) / len(rets)) ** 0.5
            score = max(-1, min(1, vol * 30))  # 高ボラはbreakoutに有利

    elif "news" in feature or "sentiment" in feature:
        # ニュース見出しの簡易感情分析
        positive_words = ["beat", "growth", "surge", "record", "upgrade", "positive"]
        negative_words = ["miss", "decline", "fall", "concern", "downgrade", "negative"]
        text = " ".join(ctx.news_headlines).lower()
        pos = sum(1 for w in positive_words if w in text)
        neg = sum(1 for w in negative_words if w in text)
        if pos + neg > 0:
            score = (pos - neg) / (pos + neg)

    else:
        # 不明な特徴量はニュートラル
        score = 0.0

    # 仮説の方向性と一致するか
    if direction == Action.LONG:
        return score
    elif direction == Action.SHORT:
        return -score
    else:  # NEUTRAL
        return 1.0 - abs(score)  # 動きが小さいほど良い


class EvaluatorAgent(Agent):
    """Generator/Evaluator 分離型エージェント

    手順:
    1. LLM 1 回で K 個の仮説を生成
    2. 各仮説を数値関数で評価
    3. 最高スコアの仮説を採用

    総コスト: 1 回の API 呼び出し
    """

    def __init__(
        self,
        k_hypotheses: int = 5,
        client: LLMClient | None = None,
        name: str = "Evaluator",
    ):
        super().__init__(name)
        self.client = client or get_default_client()
        self.k = k_hypotheses

    def decide(self, ctx: MarketContext) -> Decision:
        with Timer() as t:
            response = self.client.complete(
                system=GENERATOR_PROMPT.format(k=self.k),
                user=ctx.summary(),
                max_tokens=512,
            )
            hypotheses = parse_hypotheses(response.text)

        # 数値評価（LLM 使わない）
        if not hypotheses:
            # フォールバック
            return Decision(
                action=Action.NEUTRAL,
                confidence=0.3,
                reasoning="No hypotheses parsed, defaulting to neutral.",
                tokens_used=response.total_tokens,
                api_calls=1,
                elapsed_seconds=t.elapsed,
                metadata={"agent_type": "evaluator", "hypotheses": []},
            )

        scored = [(h, numerical_evaluator(h, ctx)) for h in hypotheses]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_hyp, best_score = scored[0]

        # 確信度は最高スコアと2番目の差で決める
        if len(scored) > 1:
            second = scored[1][1]
            confidence = max(0.3, min(0.95, 0.5 + (best_score - second) * 0.5))
        else:
            confidence = 0.5 + abs(best_score) * 0.3

        reasoning = (
            f"Generated {len(hypotheses)} hypotheses, scored numerically. "
            f"Best: {best_hyp['direction'].value} via {best_hyp['feature']} "
            f"(score={best_score:.2f}). {best_hyp['rationale']}"
        )

        return Decision(
            action=best_hyp["direction"],
            confidence=confidence,
            reasoning=reasoning,
            tokens_used=response.total_tokens,
            api_calls=1,
            elapsed_seconds=t.elapsed,
            metadata={
                "agent_type": "evaluator",
                "n_hypotheses": len(hypotheses),
                "best_score": best_score,
                "scored_hypotheses": [
                    {
                        "direction": h["direction"].value,
                        "feature": h["feature"],
                        "score": s,
                    }
                    for h, s in scored
                ],
            },
        )
