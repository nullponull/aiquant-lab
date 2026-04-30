"""J-PlatPat 自動検索 (毎日 1-2 キーワード、少量取得 → スコアリング → shortlist)

「ちょっとずつ」運用想定。1 日の作業:
- キーワード 1 つを自動選択 (日付ベース)
- 最大 20 件取得 (期限切れ年代フィルタ後)
- Claude スコアリング
- ショートリスト追記

実行:
    # 今日のキーワードで自動実行
    uv run python automation/patent_mine/run_jplatpat_daily.py
    # キーワード指定
    uv run python automation/patent_mine/run_jplatpat_daily.py --keyword "ペット 自動給水 サイフォン"
    # カテゴリの全キーワードを順次（時間かかるので手動推奨）
    uv run python automation/patent_mine/run_jplatpat_daily.py --category pet
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from keywords import CATEGORY_KEYWORDS, get_keyword_for_today
from scorer import score_patent
from run_pilot import generate_shortlist_md

DATA_DIR = HERE / "data" / "raw_jplatpat"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("jplatpat_daily")


def fetch_via_subprocess(keyword: str, max_results: int = 20,
                         pub_year_from: int = 2000, pub_year_to: int = 2005) -> list[dict]:
    """system python3 経由で playwright 起動（uv の python では playwright 未インストール）"""
    bridge = f"""
import json, sys
sys.path.insert(0, '{HERE}')
from sources.jplatpat import search_jplatpat
results = search_jplatpat(
    keyword={json.dumps(keyword, ensure_ascii=False)},
    max_results={max_results},
    pub_year_from={pub_year_from},
    pub_year_to={pub_year_to},
    headless=True,
)
print(json.dumps(results, ensure_ascii=False))
"""
    try:
        r = subprocess.run(
            ["/usr/bin/python3", "-c", bridge],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        logger.error("[fetch] timeout")
        return []
    if r.returncode != 0:
        logger.error(f"[fetch] exit {r.returncode}: {r.stderr[-300:]}")
        return []

    last_line = ""
    for line in reversed(r.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            last_line = line
            break
    if not last_line:
        logger.error("[fetch] no JSON output")
        return []
    try:
        return json.loads(last_line)
    except json.JSONDecodeError as e:
        logger.error(f"[fetch] parse error: {e}")
        return []


def process_keyword(category: str, keyword: str, max_results: int = 20) -> dict:
    """1 キーワードの完全パイプライン"""
    today = datetime.now().strftime("%Y-%m-%d")
    safe_kw = keyword.replace(" ", "_").replace("/", "_")[:50]

    logger.info(f"=== category={category}, keyword={keyword} ===")

    # 1. J-PlatPat 検索
    raw = fetch_via_subprocess(keyword, max_results=max_results)
    raw_path = DATA_DIR / f"{today}_{category}_{safe_kw}.json"
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"  取得: {len(raw)} 件 (期限切れ年代フィルタ済) → {raw_path.name}")

    if not raw:
        logger.warning("  期限切れ範囲の特許がヒットせず")
        return {"keyword": keyword, "fetched": 0, "scored": 0, "viable": 0}

    # 2. Claude スコアリング
    scored: list[dict] = []
    for i, p in enumerate(raw, 1):
        logger.info(f"  [{i}/{len(raw)}] {p['patent_number']}: {p['title'][:50]}")
        result = score_patent(p)
        if "_error" in result:
            logger.warning(f"    ✗ {result['_error']}")
            continue
        result["patent_number"] = p["patent_number"]
        result["title"] = p["title"]
        result["publication_date"] = p["publication_date"]
        result["assignee"] = p["assignee"]
        result["category_hint"] = category
        result["search_keyword"] = keyword
        scored.append(result)
        cat_label = result.get("category", "?")
        total = result.get("total", 0)
        logger.info(f"    → {cat_label} (total {total}/60)")

    # 3. 結果保存
    suffix = f"jplatpat_{category}_{safe_kw}"
    json_path = RESULTS_DIR / f"scored_{today}_{suffix}.json"
    json_path.write_text(json.dumps(scored, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = RESULTS_DIR / f"shortlist_{today}_{suffix}.md"
    md = generate_shortlist_md(scored)
    md_path.write_text(md, encoding="utf-8")

    viable_n = sum(1 for s in scored if s.get("category") == "viable")
    logger.info(f"  完了: {len(scored)} スコアリング, viable={viable_n} 件")
    logger.info(f"  → {md_path.name}")
    return {"keyword": keyword, "fetched": len(raw), "scored": len(scored), "viable": viable_n}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", type=str, help="特定キーワード指定")
    parser.add_argument("--category", type=str, help="カテゴリ全キーワード実行")
    parser.add_argument("--max-results", type=int, default=20)
    args = parser.parse_args()

    if args.keyword:
        # カテゴリは推測（キーワード文字列で）
        category = "manual"
        for cat, kws in CATEGORY_KEYWORDS.items():
            if args.keyword in kws:
                category = cat
                break
        process_keyword(category, args.keyword, max_results=args.max_results)
    elif args.category:
        if args.category not in CATEGORY_KEYWORDS:
            logger.error(f"unknown category: {args.category}, choices: {list(CATEGORY_KEYWORDS.keys())}")
            return 1
        for kw in CATEGORY_KEYWORDS[args.category]:
            process_keyword(args.category, kw, max_results=args.max_results)
    else:
        # 今日のキーワード自動選択
        category, kw = get_keyword_for_today()
        process_keyword(category, kw, max_results=args.max_results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
