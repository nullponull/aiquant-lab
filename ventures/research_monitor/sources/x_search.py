"""X 検索 (xpost-community のクッキーを流用)"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .base import Source, Item


X_COOKIES_FILE = Path("/home/sol/xpost-community/.x_cookies.json")
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.7390.37 Safari/537.36"
)


class XSearchSource(Source):
    """X 検索結果をスクレイプ。xpost-community の cookie を流用。

    各キーワードについて Latest タブから最新ツイートを取得。
    """

    source_type = "x"

    def __init__(self, keyword: str, name: Optional[str] = None):
        self.keyword = keyword
        self.name = name or f"x_search_{keyword.replace(' ', '_')}"

    def fetch_recent(self, limit: int = 20) -> list[Item]:
        if not X_COOKIES_FILE.exists():
            print(f"  [{self.name}] X cookies not found")
            return []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print(f"  [{self.name}] playwright not installed in this python")
            return []

        with open(X_COOKIES_FILE) as f:
            cookies = json.load(f)

        items: list[Item] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            ctx = browser.new_context(
                locale="ja-JP",
                user_agent=DEFAULT_UA,
                viewport={"width": 1280, "height": 1600},
            )
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            try:
                import urllib.parse
                q = urllib.parse.quote(self.keyword)
                # Latest タブ
                url = f"https://x.com/search?q={q}&src=typed_query&f=live"
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(5)

                # 全 article を抽出
                tweets = page.evaluate(
                    """() => {
                        const articles = document.querySelectorAll('article');
                        return Array.from(articles).slice(0, 30).map(a => {
                            const link = a.querySelector('a[href*="/status/"]');
                            const status_url = link ? link.getAttribute('href') : null;
                            const author_link = a.querySelector('[data-testid="User-Name"] a[href^="/"]');
                            const author = author_link ? author_link.getAttribute('href').replace(/^\\//, '') : null;
                            const txt = a.innerText || '';
                            return {
                                url: status_url ? ('https://x.com' + status_url) : null,
                                author: author,
                                text: txt.substring(0, 800),
                            };
                        });
                    }"""
                )

                for t in tweets[:limit]:
                    if not t.get("url"):
                        continue
                    items.append(
                        Item(
                            source=self.name,
                            source_type=self.source_type,
                            title=t["text"][:80],
                            url=t["url"],
                            body=t["text"],
                            author=t.get("author"),
                            published_at="",
                            raw_data={"keyword": self.keyword},
                        )
                    )
            except Exception as e:
                print(f"  [{self.name}] error: {e}")
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        return items
