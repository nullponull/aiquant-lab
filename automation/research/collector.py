#!/usr/bin/env python3
"""日次リサーチコレクター メインスクリプト

複数ソースから記事/ツイートを取得 → Claude CLI で分類 → 日次 digest 生成。

使い方:
    uv run python automation/research/collector.py [--dry-run] [--no-classify] [--no-x]

systemd timer から呼ばれる想定 (毎日 23:00)。
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

# パス設定
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sources import (
    YAHOO_FINANCE_JP,
    TOYO_KEIZAI,
    NIKKEI_MARKET,
    NoteTagSource,
)
# X は subprocess で別途呼ぶ (playwright が system python のため)


PROJECT_ROOT = HERE.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "research_inbox"
ARCHIVE_DIR = Path("/home/sol/brain-post-system/aiquant_products/assets/research_sources")

X_KEYWORDS = [
    "AI 投資 自動化",
    "ChatGPT 株",
    "AI 自動売買 月利",
    "Claude 投資",
    "AI クオンツ",
]

NOTE_TAGS = [
    "投資",
    "AI投資",
    "NISA",
    "つみたてNISA",
    "クオンツ",
    "AI副業",
]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("research-collector")


def fetch_x_via_subprocess(keywords: list[str], limit: int = 15) -> list[dict]:
    """X 検索は system python3 経由 (playwright が system にある)"""
    import subprocess

    bridge = """
import json, sys, os
sys.path.insert(0, os.path.join(os.environ.get('PROJECT_ROOT', '/home/sol/aiquant-lab'), 'automation', 'research'))
from sources.x_search import XSearchSource

payload = json.loads(sys.stdin.read())
items = []
for kw in payload['keywords']:
    src = XSearchSource(kw)
    for it in src.fetch_recent(limit=payload.get('limit', 15)):
        items.append(it.to_dict())
print(json.dumps(items, ensure_ascii=False))
"""
    system_python = "/usr/bin/python3"
    if not Path(system_python).exists():
        system_python = "python3"

    try:
        r = subprocess.run(
            [system_python, "-c", bridge],
            input=json.dumps({"keywords": keywords, "limit": limit}),
            capture_output=True,
            text=True,
            timeout=600,
            env={
                **__import__("os").environ,
                "PROJECT_ROOT": str(PROJECT_ROOT),
            },
        )
    except subprocess.TimeoutExpired:
        logger.warning("X bridge timeout")
        return []

    if r.returncode != 0:
        logger.warning(f"X bridge exit {r.returncode}: {r.stderr[-200:]}")
        return []

    last_line = ""
    for line in reversed(r.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            last_line = line
            break

    if not last_line:
        return []

    try:
        return json.loads(last_line)
    except json.JSONDecodeError:
        return []


def collect_all(no_x: bool = False) -> list[dict]:
    """全ソースから収集して dict のリストで返す"""
    all_items: list[dict] = []

    # RSS
    for src in [YAHOO_FINANCE_JP, TOYO_KEIZAI, NIKKEI_MARKET]:
        logger.info(f"Fetching: {src.name}")
        try:
            for item in src.fetch_recent(limit=30):
                all_items.append(item.to_dict())
        except Exception as e:
            logger.warning(f"  error: {e}")

    # note タグ
    for tag in NOTE_TAGS:
        logger.info(f"Fetching: note tag '{tag}'")
        try:
            src = NoteTagSource(tag)
            for item in src.fetch_recent(limit=15):
                all_items.append(item.to_dict())
        except Exception as e:
            logger.warning(f"  error: {e}")

    # X
    if not no_x:
        logger.info(f"Fetching: X (keywords {len(X_KEYWORDS)})")
        try:
            x_items = fetch_x_via_subprocess(X_KEYWORDS, limit=10)
            all_items.extend(x_items)
            logger.info(f"  X: {len(x_items)} items")
        except Exception as e:
            logger.warning(f"  error: {e}")

    # 重複除去 (URL ベース)
    seen: set[str] = set()
    deduped: list[dict] = []
    for it in all_items:
        url = it.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(it)

    logger.info(f"Total fetched: {len(all_items)}, deduped: {len(deduped)}")
    return deduped


def classify_all(items: list[dict]) -> list[dict]:
    """全アイテムを Claude CLI で分類 (時間かかる)"""
    from classifier import classify_item

    results: list[dict] = []
    for i, item in enumerate(items, 1):
        if i % 10 == 0:
            logger.info(f"  classifying {i}/{len(items)}...")
        cls = classify_item(item)
        results.append({"item": item, "classification": cls})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="LLM 分類を実行せず収集のみ")
    parser.add_argument("--no-classify", action="store_true", help="分類スキップ (デバッグ用)")
    parser.add_argument("--no-x", action="store_true", help="X スキップ (高速デバッグ用)")
    parser.add_argument("--limit-classify", type=int, default=200, help="分類する最大アイテム数")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = DATA_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== 日次リサーチ {today} ===")

    # 1. 収集
    all_items = collect_all(no_x=args.no_x)
    (out_dir / "raw_items.json").write_text(
        json.dumps(all_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"raw_items.json saved: {len(all_items)} items")

    if args.dry_run or args.no_classify:
        logger.info("分類スキップ (--dry-run / --no-classify)")
        return 0

    # 2. 分類
    target = all_items[: args.limit_classify]
    if len(all_items) > args.limit_classify:
        logger.info(f"全 {len(all_items)} 件のうち先頭 {args.limit_classify} 件のみ分類")

    classified = classify_all(target)

    # 3. フィルタ (score >= 6)
    filtered = [c for c in classified if c["classification"]["score"] >= 6]
    logger.info(f"フィルタ通過 (score>=6): {len(filtered)} 件")

    (out_dir / "filtered.json").write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 4. digest 生成
    from digest import generate_digest

    md = generate_digest(today, all_items, filtered)
    (out_dir / "digest.md").write_text(md, encoding="utf-8")
    logger.info(f"digest.md saved")

    # 5. 高評価アイテム (score>=8) は research_sources/ にも残す
    high_score = [c for c in filtered if c["classification"]["score"] >= 8]
    if high_score:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = ARCHIVE_DIR / f"{today}_collector_top.md"
        archive_lines: list[str] = []
        archive_lines.append(f"# {today} 高評価アイテム (score >= 8)")
        archive_lines.append("")
        archive_lines.append(f"自動収集: {datetime.now().isoformat()}")
        archive_lines.append("")
        for c in high_score:
            it = c["item"]
            cls = c["classification"]
            archive_lines.append(f"## [{cls['score']}/10 {cls['category']}] {it['title'][:80]}")
            archive_lines.append("")
            archive_lines.append(f"- 出典: {it['source']} | URL: {it['url']}")
            if it.get("author"):
                archive_lines.append(f"- 著者: {it['author']}")
            archive_lines.append(f"- 判定: {cls.get('reason','')}")
            body = (it.get("body") or "").replace("\n", " ")[:300]
            if body:
                archive_lines.append("")
                archive_lines.append(f"> {body}")
            archive_lines.append("")
        archive_path.write_text("\n".join(archive_lines), encoding="utf-8")
        logger.info(f"高評価アイテム保存: {archive_path}")

    logger.info("=== 完了 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
