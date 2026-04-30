"""Amazon JP 自動検索による競合データ取得"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
from typing import Optional


def search_amazon_jp(query: str, max_results: int = 12, headless: bool = True) -> dict:
    """Amazon JP で商品検索 → 構造化データ返却

    Returns:
        {
            "query": str,
            "fetched_at": str,
            "competitors": [...],
            "price_distribution": {min, max, median},
            "saturation_level": "low/medium/high",
            "_error": str (失敗時のみ),
        }
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"_error": "playwright not installed"}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            locale="ja-JP",
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 1800},
        )
        page = ctx.new_page()
        try:
            url = f"https://www.amazon.co.jp/s?k={urllib.parse.quote(query)}"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(8)

            products = page.evaluate(
                """(maxN) => {
                    const items = document.querySelectorAll('[data-component-type="s-search-result"]');
                    return Array.from(items).slice(0, maxN).map(item => {
                        const title_el = item.querySelector('h2 a span, h2 span');
                        const price_el = item.querySelector('.a-price .a-offscreen');
                        const rating_el = item.querySelector('.a-icon-star-small .a-icon-alt, .a-icon-star .a-icon-alt');
                        const review_el = item.querySelector('.a-size-base.s-underline-text');
                        const sponsored = !!item.querySelector('[aria-label*="スポンサー"]');
                        return {
                            title: title_el ? title_el.textContent.substring(0, 150).trim() : '',
                            price_text: price_el ? price_el.textContent.trim() : '',
                            rating: rating_el ? rating_el.textContent.trim() : '',
                            reviews: review_el ? review_el.textContent.trim() : '',
                            sponsored: sponsored
                        };
                    }).filter(p => p.title);
                }""",
                max_results,
            )

            # 価格を数値に
            import re
            prices: list[int] = []
            for p_ in products:
                m = re.search(r"[\d,]+", p_.get("price_text", ""))
                if m:
                    try:
                        p_["price_jpy"] = int(m.group(0).replace(",", ""))
                        prices.append(p_["price_jpy"])
                    except ValueError:
                        p_["price_jpy"] = None
                else:
                    p_["price_jpy"] = None

            # 価格分布
            price_dist: dict = {}
            if prices:
                prices.sort()
                price_dist = {
                    "min": prices[0],
                    "max": prices[-1],
                    "median": prices[len(prices) // 2],
                    "avg": sum(prices) // len(prices),
                    "count": len(prices),
                }

            # 飽和度判定: スポンサー比率 + 価格分散
            n_sponsored = sum(1 for p_ in products if p_.get("sponsored"))
            sponsored_ratio = n_sponsored / max(1, len(products))
            if sponsored_ratio >= 0.5:
                saturation = "high"
            elif sponsored_ratio >= 0.25:
                saturation = "medium"
            else:
                saturation = "low"

            from datetime import datetime
            result = {
                "query": query,
                "fetched_at": datetime.now().isoformat(),
                "competitors": products,
                "price_distribution": price_dist,
                "saturation_level": saturation,
                "sponsored_ratio": round(sponsored_ratio, 2),
            }
            browser.close()
            return result

        except Exception as e:
            try:
                browser.close()
            except Exception:
                pass
            return {"_error": f"exception: {e}"}


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "ペット 自動給水器"
    print(f"Searching: {q}")
    result = search_amazon_jp(q, max_results=12)
    if "_error" in result:
        print(f"ERROR: {result['_error']}")
    else:
        print(f"Competitors: {len(result['competitors'])}")
        print(f"Price dist: {result['price_distribution']}")
        print(f"Saturation: {result['saturation_level']} (sponsored {result['sponsored_ratio']*100:.0f}%)")
        for i, p in enumerate(result["competitors"][:5], 1):
            print(f"\n{i}. {p['title'][:80]}")
            print(f"   Price: {p.get('price_text', '?')} ({p.get('price_jpy', '?')})")
