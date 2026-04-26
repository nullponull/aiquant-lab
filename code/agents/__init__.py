"""LLM エージェント実装群

Episode 2 の比較実験用：
- SoloAgent: 単一LLM呼び出し
- DebateAgent: N体エージェントの議論
- EvaluatorAgent: Generator/Evaluator 分離パターン
- BaselineAgent: ルールベース（コントロール群）
"""

from .base import Agent, Decision, MarketContext
from .solo import SoloAgent
from .debate import DebateAgent
from .evaluator import EvaluatorAgent
from .baseline import BaselineAgent

__all__ = [
    "Agent",
    "Decision",
    "MarketContext",
    "SoloAgent",
    "DebateAgent",
    "EvaluatorAgent",
    "BaselineAgent",
]
