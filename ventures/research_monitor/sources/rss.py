"""RSS フェッチャー (Yahoo Finance JP / ダイヤモンド / 東洋経済 など)"""

from __future__ import annotations

import re
from typing import Optional
import urllib.request
from xml.etree import ElementTree as ET

from .base import Source, Item


KEYWORD_FILTER = ["投資", "AI", "NISA", "株", "ChatGPT", "クオンツ", "つみたて", "副業", "資産", "為替", "暗号通貨"]


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _matches_keywords(title: str, body: str) -> bool:
    s = (title + " " + body).lower()
    for kw in KEYWORD_FILTER:
        if kw.lower() in s:
            return True
    return False


class RSSSource(Source):
    """RSS / Atom feed を取得して Item に変換"""

    source_type = "rss"

    def __init__(self, name: str, feed_url: str, filter_keywords: bool = True):
        self.name = name
        self.feed_url = feed_url
        self.filter_keywords = filter_keywords

    def fetch_recent(self, limit: int = 50) -> list[Item]:
        try:
            req = urllib.request.Request(
                self.feed_url,
                headers={"User-Agent": "Mozilla/5.0 (aiquant-research-collector)"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                xml_bytes = resp.read()
        except Exception as e:
            print(f"  [{self.name}] fetch error: {e}")
            return []

        items: list[Item] = []
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            print(f"  [{self.name}] parse error: {e}")
            return []

        # RSS 2.0
        for entry in root.iter("item"):
            title = _strip_html((entry.findtext("title") or "").strip())
            link = (entry.findtext("link") or "").strip()
            description = _strip_html((entry.findtext("description") or "").strip())
            pub = (entry.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            if self.filter_keywords and not _matches_keywords(title, description):
                continue
            items.append(
                Item(
                    source=self.name,
                    source_type=self.source_type,
                    title=title,
                    url=link,
                    body=description,
                    published_at=pub,
                )
            )
            if len(items) >= limit:
                break

        if items:
            return items

        # Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = _strip_html((entry.findtext("atom:title", default="", namespaces=ns) or "").strip())
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href") if link_el is not None else ""
            summary = _strip_html((entry.findtext("atom:summary", default="", namespaces=ns) or "").strip())
            updated = (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
            if not title or not link:
                continue
            if self.filter_keywords and not _matches_keywords(title, summary):
                continue
            items.append(
                Item(
                    source=self.name,
                    source_type=self.source_type,
                    title=title,
                    url=link,
                    body=summary,
                    published_at=updated,
                )
            )
            if len(items) >= limit:
                break

        return items


# 主要 RSS フィード定義
YAHOO_FINANCE_JP = RSSSource(
    name="yahoo_finance_jp",
    feed_url="https://news.yahoo.co.jp/rss/categories/business.xml",
)

DIAMOND_ONLINE = RSSSource(
    name="diamond_online",
    feed_url="https://diamond.jp/list/feed/category/economics_money",
)

TOYO_KEIZAI = RSSSource(
    name="toyo_keizai",
    feed_url="https://toyokeizai.net/list/feed/rss",
)

NIKKEI_MARKET = RSSSource(
    name="nikkei_market",
    feed_url="https://news.yahoo.co.jp/rss/media/nikkeisty/all.xml",
)
