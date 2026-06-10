"""ソース共通インターフェース"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Item:
    """収集アイテムの共通形式"""
    source: str           # "yahoo_finance_jp" 等
    source_type: str      # "rss" / "note" / "x"
    title: str
    url: str
    body: str = ""        # 本文 (取得できれば)
    author: Optional[str] = None
    published_at: Optional[str] = None  # ISO8601
    raw_data: dict = field(default_factory=dict)  # 元データ全部
    fetched_at: str = ""

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def short_id(self) -> str:
        """重複検出用のキー"""
        return f"{self.source}:{self.url}"


class Source:
    """全ソースの基底クラス"""

    name: str = "unknown"
    source_type: str = "unknown"

    def fetch_recent(self, limit: int = 50) -> list[Item]:
        raise NotImplementedError

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name}>"
