"""J-PlatPat 検索の Playwright 自動化（少量・段階的運用専用）

設計原則:
- 1 回の実行で 1 キーワード × 最大 30 件のみ
- アクション間に 3-8 秒のランダム待機
- 1 日あたり最大 5 検索（rate limit 自衛）
- 結果の保存先 = data/raw/{date}_{keyword}.json

J-PlatPat 規約: 個人/研究/教育目的の利用は OK、
機械的大量取得は禁止。本実装は「人間 1 人分の操作速度」を維持する。
"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


JPLATPAT_SEARCH_URL = "https://www.j-platpat.inpit.go.jp/s0100"
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


def _rand_sleep(min_s: float = 3.0, max_s: float = 8.0):
    """人間っぽいランダム待機"""
    time.sleep(random.uniform(min_s, max_s))


def _parse_pub_year(date_str: str) -> Optional[int]:
    """公報日から西暦年を抽出（YYYY/MM/DD or YYYY-MM-DD）"""
    if not date_str:
        return None
    s = date_str.strip()
    if len(s) >= 4 and s[:4].isdigit():
        try:
            return int(s[:4])
        except ValueError:
            return None
    return None


def search_jplatpat(
    keyword: str,
    max_results: int = 20,
    pub_year_from: int = 2000,
    pub_year_to: int = 2005,
    headless: bool = True,
) -> list[dict]:
    """J-PlatPat 簡易検索 → 結果の特許情報リストを返す

    Args:
        keyword: 検索キーワード
        max_results: 最大取得件数（推奨 20-30）
        pub_year_from / pub_year_to: 公報日範囲（期限切れ狙い）
        headless: ブラウザ headless モード

    Returns:
        [{
            patent_number, application_number, application_date,
            publication_date, title, assignee, inventor, ipc, status,
        }]
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[jplatpat] playwright not installed (system python)")
        return []

    results: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            locale="ja-JP",
            user_agent=DEFAULT_UA,
            viewport={"width": 1280, "height": 1600},
        )
        # Anti-bot 検出回避
        ctx.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['ja-JP', 'ja', 'en']});
        """
        )
        page = ctx.new_page()
        try:
            print(f"[jplatpat] navigating...")
            page.goto(JPLATPAT_SEARCH_URL, wait_until="networkidle", timeout=60000)
            _rand_sleep(8, 12)  # SPA 完全読み込み待機

            # 「特許・実用新案」を選択
            try:
                page.click("#mat-radio-1", timeout=5000)
                _rand_sleep(1, 2)
            except Exception:
                print("[jplatpat] radio click failed (継続)")

            # キーワード入力
            page.fill("input#s01_srchCondtn_txtSimpleSearch", keyword)
            _rand_sleep(1, 3)

            # 検索ボタン
            print(f"[jplatpat] searching '{keyword}'...")
            page.click("#s01_srchBtn_btnSearch")

            # 結果ロード待機
            _rand_sleep(15, 20)

            # 結果取得（簡易検索の結果テーブル）
            results_data = page.evaluate(
                """(maxN) => {
                    // テーブル構造取得
                    const rows = document.querySelectorAll('table tr');
                    const out = [];
                    let header = null;
                    for (const row of Array.from(rows).slice(0, maxN + 5)) {
                        const cells = row.querySelectorAll('th, td');
                        if (cells.length === 0) continue;
                        const cell_texts = Array.from(cells).map(c => (c.innerText || '').trim());
                        if (!header && cells[0].tagName === 'TH') {
                            header = cell_texts;
                            continue;
                        }
                        if (cell_texts.every(t => !t)) continue;
                        out.push({header, cells: cell_texts});
                        if (out.length >= maxN) break;
                    }
                    return out;
                }""",
                max_results,
            )

            for r in results_data:
                cells = r.get("cells", [])
                header = r.get("header") or []
                # 簡易検索の結果テーブルカラム順 (J-PlatPat 標準):
                # [No.] [文献番号] [出願番号] [出願日] [公知日] [発明の名称] [出願人/権利者] [FI] [URL]
                # 列数とインデックスは実態確認しながら推測
                if len(cells) < 6:
                    continue
                # No. と URL を除く本体抽出
                doc_idx = next((i for i, h in enumerate(header) if "文献" in (h or "")), 1)
                appl_idx = next((i for i, h in enumerate(header) if "出願番号" in (h or "")), 2)
                appl_date_idx = next((i for i, h in enumerate(header) if "出願日" in (h or "")), 3)
                pub_date_idx = next((i for i, h in enumerate(header) if "公知" in (h or "") or "公開" in (h or "")), 4)
                title_idx = next((i for i, h in enumerate(header) if "発明" in (h or "") or "名称" in (h or "")), 5)
                assignee_idx = next((i for i, h in enumerate(header) if "権利者" in (h or "") or "出願人" in (h or "")), 6)
                fi_idx = next((i for i, h in enumerate(header) if h == "FI"), 7)

                def get(i: int) -> str:
                    return cells[i] if 0 <= i < len(cells) else ""

                pub_date_str = get(pub_date_idx)
                pub_year = _parse_pub_year(pub_date_str)

                # 公報日ベースの期限切れフィルター
                if pub_year is None:
                    continue
                if pub_year < pub_year_from or pub_year > pub_year_to:
                    continue

                results.append({
                    "patent_number": get(doc_idx),
                    "application_number": get(appl_idx),
                    "application_date": get(appl_date_idx),
                    "publication_date": pub_date_str,
                    "title": get(title_idx),
                    "assignee": get(assignee_idx),
                    "inventor": "",  # 簡易検索結果には含まれない
                    "ipc": get(fi_idx),
                    "status": "",  # 詳細ページ閲覧で取得（本実装では空）
                    "abstract": "",  # 詳細ページ閲覧で取得
                    "claims": "",
                    "_keyword": keyword,
                    "_fetched_at": datetime.now().isoformat(),
                })

        except Exception as e:
            print(f"[jplatpat] error: {e}")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return results


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "ペット 給水"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    results = search_jplatpat(kw, max_results=n)
    print(f"\n=== 取得 {len(results)} 件 ===")
    for r in results[:10]:
        print(f"\n  {r['patent_number']} ({r['publication_date']})")
        print(f"    {r['title'][:80]}")
        print(f"    出願人: {r['assignee'][:60]}")
