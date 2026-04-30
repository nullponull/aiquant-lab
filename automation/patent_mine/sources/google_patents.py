"""Google Patents で日本の期限切れ特許を検索

API: https://patents.google.com/xhr/query
- 認証不要
- Rate limit あり（控えめに 1-2 req/sec）
- JSON 応答
- 個別特許の詳細は patents.google.com/patent/{id} を Playwright 取得
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional


def _http_get(url: str, timeout: int = 20) -> Optional[str]:
    """Playwright (system python3 subprocess) 経由で HTTP GET。
    Google Patents は urllib/curl だと automation 検出で 503 を返すため。"""
    bridge = """
import sys, json, time
from playwright.sync_api import sync_playwright

url = sys.stdin.read().strip()
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox','--disable-blink-features=AutomationControlled'])
    ctx = browser.new_context(
        locale='ja-JP',
        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
        viewport={'width':1280,'height':900},
    )
    page = ctx.new_page()
    try:
        resp = page.goto(url, wait_until='domcontentloaded', timeout=30000)
        time.sleep(2)
        # Google Patents の xhr/query は JSON を <pre> に入れて返す
        body = page.evaluate("document.body.innerText")
        if body and body.strip().startswith('{'):
            print(body)
        else:
            # HTML 詳細ページ
            print(page.content())
    except Exception as e:
        print(json.dumps({'error': str(e)}))
    finally:
        browser.close()
"""
    try:
        r = subprocess.run(
            ["/usr/bin/python3", "-c", bridge],
            input=url, capture_output=True, text=True, timeout=timeout + 30,
        )
        if r.returncode != 0:
            return None
        return r.stdout
    except (subprocess.TimeoutExpired, Exception):
        return None


GOOGLE_PATENTS_QUERY_URL = "https://patents.google.com/xhr/query"


@dataclass
class PatentSearchResult:
    patent_id: str  # e.g. "patent/JP6261826B2/ja"
    patent_number: str  # e.g. "JP-2005-XXX-A"
    title: str
    snippet: str
    publication_date: str
    inventor: str = ""
    assignee: str = ""
    raw: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _build_url(
    keyword: str,
    country: str = "JP",
    status: str = "GRANT",
    pub_date_from: Optional[str] = None,
    pub_date_to: Optional[str] = None,
    page: int = 0,
) -> str:
    q_parts = [f"q={urllib.parse.quote(keyword)}"]
    q_parts.append(f"country={country}")
    if status:
        q_parts.append(f"status={status}")
    if pub_date_from:
        q_parts.append(f"after=publication:{pub_date_from}")
    if pub_date_to:
        q_parts.append(f"before=publication:{pub_date_to}")
    if page:
        q_parts.append(f"num=10")
        q_parts.append(f"oq={urllib.parse.quote(keyword)}")
        q_parts.append(f"page={page}")
    inner = "&".join(q_parts)
    return f"{GOOGLE_PATENTS_QUERY_URL}?url={urllib.parse.quote(inner)}&exp="


def search(
    keyword: str,
    country: str = "JP",
    expired_years_ago_min: int = 20,
    expired_years_ago_max: int = 25,
    max_results: int = 50,
    sleep_sec: float = 1.0,
) -> list[PatentSearchResult]:
    """期限切れ範囲の特許を検索

    特許の権利期間は出願から 20 年。公開日 (publication_date) は出願後 1.5 年程度。
    したがって「公開日から 19 年経過」を期限切れ目安とする。

    実用新案は出願から 10 年だが、公開ベースだと 9 年経過程度。
    本関数では特許のみ。
    """
    today = datetime.now()
    pub_to = (today - timedelta(days=365 * expired_years_ago_min)).strftime("%Y%m%d")
    pub_from = (today - timedelta(days=365 * expired_years_ago_max)).strftime("%Y%m%d")

    results: list[PatentSearchResult] = []
    page = 0
    while len(results) < max_results:
        url = _build_url(keyword, country=country,
                         pub_date_from=pub_from, pub_date_to=pub_to, page=page)
        body = _http_get(url, timeout=20)
        if not body:
            print(f"[google_patents] empty response page {page}")
            break
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            print(f"[google_patents] parse error page {page}: {e}")
            break

        clusters = data.get("results", {}).get("cluster", [])
        page_results = []
        for c in clusters:
            for r in c.get("result", []):
                p = r.get("patent", {})
                pid = p.get("publication_number") or p.get("patent_number") or p.get("id", "")
                pub_date = p.get("publication_date", "")
                title = p.get("title", "").replace("<b>", "").replace("</b>", "").strip()
                snippet = p.get("snippet", "").replace("<b>", "").replace("</b>", "")
                inventor = p.get("inventor", "")
                assignee = p.get("assignee", "")
                page_results.append(PatentSearchResult(
                    patent_id=r.get("id", ""),
                    patent_number=pid,
                    title=title,
                    snippet=snippet,
                    publication_date=pub_date,
                    inventor=inventor,
                    assignee=assignee,
                    raw=p,
                ))

        if not page_results:
            break
        results.extend(page_results)

        if data.get("results", {}).get("num_page", 0) >= data.get("results", {}).get("total_num_pages", 1) - 1:
            break

        page += 1
        time.sleep(sleep_sec)

    return results[:max_results]


def fetch_patent_detail(patent_url: str) -> dict:
    """個別特許ページから本文・請求項を取得

    入力: patent_url のスラッグ (例: "patent/JP6261826B2/ja") または完全URL
    出力: { title, abstract, claims, description_excerpt, ... }
    """
    if patent_url.startswith("http"):
        url = patent_url
    else:
        url = f"https://patents.google.com/{patent_url}"

    html = _http_get(url, timeout=30)
    if not html:
        return {"error": "empty response", "url": url}

    # 主要セクションを正規表現で抽出
    import re
    def extract(pattern: str, text: str) -> str:
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return (m.group(1) if m else "").strip()

    abstract = extract(r'<section[^>]*itemprop="abstract"[^>]*>(.*?)</section>', html)
    claims_raw = extract(r'<section[^>]*itemprop="claims"[^>]*>(.*?)</section>', html)
    desc = extract(r'<section[^>]*itemprop="description"[^>]*>(.*?)</section>', html)

    # HTML タグ除去
    def strip_tags(t: str) -> str:
        return re.sub(r"<[^>]+>", " ", t).replace("&nbsp;", " ").replace("　", " ")

    return {
        "url": url,
        "abstract": strip_tags(abstract)[:2000],
        "claims": strip_tags(claims_raw)[:5000],
        "description_excerpt": strip_tags(desc)[:3000],
    }


if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else "プランター"
    results = search(kw, max_results=10)
    print(f"Found: {len(results)}")
    for r in results[:5]:
        print(f"\n--- {r.patent_number} ({r.publication_date}) ---")
        print(f"Title: {r.title}")
        print(f"Inventor: {r.inventor[:80]}")
        print(f"Assignee: {r.assignee[:80]}")
        print(f"Snippet: {r.snippet[:200]}")
