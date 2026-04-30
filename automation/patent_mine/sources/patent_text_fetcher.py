"""J-PlatPat から特許本文を取得する再利用可能モジュール

検証済み URL パターン:
- 公報固定アドレス: /c1801/PU/JP-{出願番号}/20/ja
- 文献詳細 (実本文): 上記ページから「実登XXXXXXX」リンクを Playwright クリック

実 J-PlatPat は Angular SPA で javascript:void(0) ベース、
Playwright の page.click() で動作する (force=True 不要)。
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Optional


def _convert_publication_to_application_number(pub_number: str) -> Optional[str]:
    """文献番号 (実登XXXX or 特開YYYY-NNNN) を出願番号形式へ変換

    実登XXXXXXX は登録番号で、出願番号は別途 J-PlatPat 検索で取得が必要。
    特開YYYY-NNNN は出願年-シリアル番号で、出願番号 (特願YYYY-NNNNNN) と異なる。

    本関数では簡易的に「数値部分」を返し、実際は J-PlatPat 内検索で対応関係を取得する。
    """
    digits = re.sub(r"[^\d-]", "", pub_number)
    return digits


def fetch_patent_text(patent_number: str, headless: bool = True) -> dict:
    """特許番号 (実登 or 特開 etc.) から本文を取得

    Returns:
        {
            "patent_number": str,
            "application_number": str,
            "title": str,
            "abstract": str (要約),
            "claims": str (請求の範囲),
            "description": str (詳細な説明、最大 8000 字),
            "applicant": str,
            "inventor": str,
            "publication_date": str,
            "_fetched_at": str,
            "_error": str (取得失敗時のみ),
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
            viewport={"width": 1280, "height": 2400},
        )
        page = ctx.new_page()
        try:
            # Step 1: 簡易検索で出願番号を取得
            page.goto("https://www.j-platpat.inpit.go.jp/s0100", wait_until="networkidle", timeout=60000)
            time.sleep(10)
            page.click("#mat-radio-1", timeout=5000)
            time.sleep(1)
            search_query = re.sub(r"[^\d-]", "", patent_number)
            page.fill("input#s01_srchCondtn_txtSimpleSearch", search_query)
            time.sleep(1)
            page.click("#s01_srchBtn_btnSearch")
            time.sleep(15)

            # 検索結果から行内の出願番号を取得
            row_data = page.evaluate(
                """(num) => {
                    const rows = document.querySelectorAll('table tr');
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 4) continue;
                        const row_text = row.innerText || '';
                        if (row_text.includes(num)) {
                            return {
                                cells: Array.from(cells).map(c => (c.innerText||'').trim()),
                                full: row_text.substring(0, 500)
                            };
                        }
                    }
                    return null;
                }""",
                patent_number,
            )
            if not row_data:
                browser.close()
                return {"_error": f"特許 {patent_number} がリストに見つからず"}

            cells = row_data.get("cells", [])
            # 出願番号は通常 cells[1] (例: 実願2003-272390 or 特願YYYY-NNNNNN)
            application_number = ""
            for cell in cells:
                if cell.startswith(("実願", "特願")):
                    application_number = cell.replace("実願", "").replace("特願", "")
                    application_type_jp = "実願" if cell.startswith("実願") else "特願"
                    break
            if not application_number:
                browser.close()
                return {"_error": f"出願番号取得失敗、cells={cells}"}

            # Step 2: 固定アドレス URL に直接アクセス
            fixed_url = f"https://www.j-platpat.inpit.go.jp/c1801/PU/JP-{application_number}/20/ja"
            page.goto(fixed_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(12)

            # Step 3: 固定アドレスページの「実登XXXXXXX」リンクをクリック
            # 新タブで /p0200 (本文ページ) が開く挙動だが、タイミングが不安定。
            # expect_page() で確実に取得。

            text_page = None
            try:
                with ctx.expect_page(timeout=20000) as new_page_info:
                    page.click(f'a:has-text("{patent_number}")', force=True)
                text_page = new_page_info.value
                text_page.wait_for_load_state("domcontentloaded", timeout=30000)
                time.sleep(15)
            except Exception:
                # フォールバック: 同タブクリック + 待機
                time.sleep(20)
                # context.pages を確認
                for p_ in ctx.pages:
                    if "/p02" in p_.url or "p0200" in p_.url:
                        text_page = p_
                        break
                if text_page is None and len(ctx.pages) > 1:
                    text_page = ctx.pages[-1]
                if text_page is None:
                    text_page = page

            try:
                if text_page != page:
                    text_page.wait_for_load_state("domcontentloaded", timeout=30000)
                    time.sleep(10)
            except Exception:
                pass

            body = text_page.evaluate("document.body.innerText")
            if len(body) < 1000:
                browser.close()
                return {"_error": f"本文取得失敗 (text_page URL={text_page.url}, len={len(body)})"}

            # 主要セクション抽出
            def extract_section(start_kw: str, end_kws: list[str]) -> str:
                idx = body.find(start_kw)
                if idx < 0:
                    return ""
                end_idx = len(body)
                for ek in end_kws:
                    e = body.find(ek, idx + len(start_kw))
                    if e > 0 and e < end_idx:
                        end_idx = e
                return body[idx:end_idx].strip()

            abstract = extract_section("【要約】", ["請求の範囲", "詳細な説明", "図面", "次の文献"])
            claims = extract_section("請求の範囲", ["詳細な説明", "図面", "次の文献"])
            description = extract_section("詳細な説明", ["図面", "次の文献"])[:8000]

            # フォールバック: タイトル等の上部メタ情報
            title_match = re.search(r"【考案の名称】([^\n]+)", body) or re.search(r"【発明の名称】([^\n]+)", body)
            title = title_match.group(1).strip() if title_match else ""

            applicant_match = re.search(r"【出願人】.*?【氏名又は名称】([^\n]+)", body, re.DOTALL)
            applicant = applicant_match.group(1).strip() if applicant_match else ""

            inventor_match = re.search(r"【考案者】.*?【氏名】([^\n]+)", body, re.DOTALL) or re.search(r"【発明者】.*?【氏名】([^\n]+)", body, re.DOTALL)
            inventor = inventor_match.group(1).strip() if inventor_match else ""

            from datetime import datetime
            result = {
                "patent_number": patent_number,
                "application_number": application_number,
                "title": title,
                "abstract": abstract,
                "claims": claims,
                "description": description,
                "applicant": applicant,
                "inventor": inventor,
                "_fetched_at": datetime.now().isoformat(),
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
    pn = sys.argv[1] if len(sys.argv) > 1 else "実登3101582"
    print(f"Fetching {pn}...")
    result = fetch_patent_text(pn)
    if "_error" in result:
        print(f"ERROR: {result['_error']}")
    else:
        print(f"\nTitle: {result['title']}")
        print(f"Applicant: {result['applicant']}")
        print(f"Inventor: {result['inventor']}")
        print(f"\n=== Abstract ===\n{result['abstract'][:1000]}")
        print(f"\n=== Claims ===\n{result['claims'][:2000]}")
        print(f"\n=== Description (excerpt) ===\n{result['description'][:1500]}")
