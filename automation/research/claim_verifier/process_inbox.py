"""research_inbox の filtered.json から主張を抽出して DB に登録 + T=0 スナップ"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from db import insert_claim, update_claim_snapshot
from claim_extractor import extract_claim, claim_to_db_record
from snapshot import fetch_price


PROJECT_ROOT = HERE.parent.parent.parent
INBOX_DIR = PROJECT_ROOT / "data" / "research_inbox"


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("process_inbox")


def process_date(date_str: str) -> tuple[int, int]:
    """指定日付の filtered.json を処理

    Returns: (extracted, registered)
    """
    f = INBOX_DIR / date_str / "filtered.json"
    if not f.exists():
        logger.info(f"filtered.json なし: {date_str}")
        return (0, 0)

    with open(f) as fh:
        entries = json.load(fh)

    if not isinstance(entries, list):
        return (0, 0)

    logger.info(f"=== {date_str}: {len(entries)} 件 ===")

    extracted_count = 0
    registered_count = 0

    for entry in entries:
        # entry は {"item": {...}, "classification": {...}}
        item = entry.get("item", {}) if "item" in entry else entry
        cls = entry.get("classification", {})

        # スコア低いものはスキップ
        if cls.get("score", 0) < 6:
            continue
        # discard は不要
        if cls.get("category") == "discard":
            continue

        logger.info(f"  抽出中: {item.get('title','')[:60]}...")
        result = extract_claim(item)
        if not result.get("is_claimable"):
            continue

        extracted_count += 1
        for claim in result["claims"]:
            record = claim_to_db_record(item, claim)

            # T=0 スナップショット
            snap = fetch_price(claim["asset"])
            if snap is None:
                logger.warning(f"    snapshot 失敗: {claim['asset']}")
                continue
            record["entry_snapshot_price"] = snap["price"]
            record["entry_currency"] = snap["currency"]
            record["entry_snapshot_at"] = datetime.utcnow().isoformat()

            claim_id = insert_claim(record)
            if claim_id:
                registered_count += 1
                logger.info(f"    ✓ claim #{claim_id}: {claim['asset']} {claim['direction']} "
                            f"horizon {claim['horizon_hours']}h, entry {snap['price']:.4f} {snap['currency']}")
            else:
                logger.info(f"    重複（既存）: {claim['asset']} {claim['direction']}")

    logger.info(f"  抽出: {extracted_count} 件、新規登録: {registered_count} 件")
    return (extracted_count, registered_count)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None,
                        help="YYYY-MM-DD 形式、省略時は今日")
    parser.add_argument("--all", action="store_true",
                        help="research_inbox 配下のすべての日付を処理")
    args = parser.parse_args()

    if args.all:
        dates = sorted([d.name for d in INBOX_DIR.iterdir() if d.is_dir()])
        for date_str in dates:
            process_date(date_str)
    else:
        date_str = args.date or datetime.now().strftime("%Y-%m-%d")
        process_date(date_str)


if __name__ == "__main__":
    main()
