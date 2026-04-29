"""note 検索 API"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .base import Source, Item


class NoteTagSource(Source):
    """note 検索 API でキーワード（タグ相当）の最新記事を取得

    エンドポイント: https://note.com/api/v3/searches?context=note&q={keyword}&size={n}
    """

    source_type = "note"

    def __init__(self, keyword: str):
        self.keyword = keyword
        self.name = f"note_search_{keyword}"

    def fetch_recent(self, limit: int = 20) -> list[Item]:
        encoded = urllib.parse.quote(self.keyword)
        url = (
            "https://note.com/api/v3/searches?"
            f"context=note&q={encoded}&size={limit}&start=0"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (aiquant-research-collector)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  [{self.name}] fetch error: {e}")
            return []

        notes = (
            data.get("data", {}).get("notes", {}).get("contents", [])
            or data.get("data", {}).get("contents", [])
            or []
        )
        items: list[Item] = []
        for n in notes[:limit]:
            user = (n.get("user") or {})
            note_key = n.get("key", "")
            url = (
                n.get("note_url")
                or (f"https://note.com/{user.get('urlname','')}/n/{note_key}" if note_key else "")
            )
            if not url:
                continue
            items.append(
                Item(
                    source=self.name,
                    source_type=self.source_type,
                    title=n.get("name", "") or "",
                    url=url,
                    body=(n.get("description") or n.get("highlight") or "")[:500],
                    author=user.get("nickname") or user.get("urlname"),
                    published_at=n.get("publish_at") or "",
                    raw_data={
                        "like_count": n.get("like_count"),
                        "price": n.get("price"),
                        "comment_count": n.get("comment_count"),
                    },
                )
            )
        return items
