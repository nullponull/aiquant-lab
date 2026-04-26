"""エージェント共通インターフェース"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class Action(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


@dataclass
class MarketContext:
    """市場の状況をエージェントに提示するためのコンテキスト"""
    symbol: str
    date: str
    recent_prices: list[float]  # 直近20日の終値
    news_headlines: list[str]   # 直近のニュース見出し
    macro_indicators: dict[str, float] = field(default_factory=dict)
    horizon_days: int = 5  # 何営業日後の判定か

    def summary(self) -> str:
        """LLM に渡す自然言語のサマリー"""
        prices_str = ", ".join(f"{p:.2f}" for p in self.recent_prices[-5:])
        news_str = "\n".join(f"- {h}" for h in self.news_headlines[:5])
        return (
            f"Symbol: {self.symbol}\n"
            f"Date: {self.date}\n"
            f"Last 5 closes: {prices_str}\n"
            f"Recent news:\n{news_str}\n"
            f"Decision horizon: {self.horizon_days} business days"
        )


@dataclass
class Decision:
    """エージェントの最終判断"""
    action: Action
    confidence: float  # 0.0 - 1.0
    reasoning: str
    tokens_used: int = 0
    api_calls: int = 0
    elapsed_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)


class Agent:
    """全エージェントの抽象基底クラス"""

    def __init__(self, name: str):
        self.name = name

    def decide(self, ctx: MarketContext) -> Decision:
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name}>"


class Timer:
    """簡易タイマー"""
    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.elapsed = time.time() - self.start
