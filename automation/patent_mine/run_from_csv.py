"""J-PlatPat CSV → Claude スコアリング → Shortlist 生成

使い方:
    1. https://www.j-platpat.inpit.go.jp/s0100 で検索
       推奨フィルタ:
       - 「特許・実用新案」を選択
       - キーワード（例: ペット 給水, 介護 立ち上がり, 折り畳み 物干し）
       - 公報発行日: 2000-01-01 〜 2005-12-31 (20年以上前)
    2. 「CSV出力」ボタンで結果をダウンロード
    3. CSV をプロジェクトの data/ に置く
    4. uv run python automation/patent_mine/run_from_csv.py path/to/your_export.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from jplatpat_csv_loader import load_csv
from scorer import score_patent
from run_pilot import generate_shortlist_md

RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("patent_mine_csv")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="J-PlatPat CSV エクスポートのパス")
    parser.add_argument("--max", type=int, default=100, help="スコアリングする最大件数")
    parser.add_argument("--output-suffix", type=str, default="",
                        help="出力ファイル名のサフィックス (カテゴリ名等)")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        logger.error(f"CSV not found: {csv_path}")
        return 1

    logger.info(f"=== J-PlatPat CSV processing: {csv_path.name} ===")
    patents = load_csv(csv_path)

    if len(patents) > args.max:
        logger.info(f"全 {len(patents)} 件のうち先頭 {args.max} 件をスコアリング")
        patents = patents[:args.max]

    if not patents:
        logger.warning("期限切れ特許が見つかりません")
        return 0

    logger.info(f"スコアリング対象: {len(patents)} 件")
    scored: list[dict] = []
    for i, p in enumerate(patents, 1):
        logger.info(f"  [{i}/{len(patents)}] {p['patent_number']}: {p['title'][:50]}")
        result = score_patent(p)
        if "_error" in result:
            logger.warning(f"    ✗ {result['_error']}")
            continue
        # 入力情報をマージ
        result["patent_number"] = p["patent_number"]
        result["title"] = p["title"]
        result["publication_date"] = p["publication_date"]
        result["assignee"] = p["assignee"]
        result["category_hint"] = p.get("ipc", "")[:30]
        scored.append(result)
        cat = result.get("category", "?")
        total = result.get("total", 0)
        margin = result.get("estimated_margin_pct", 0)
        logger.info(f"    → {cat} (total {total}/60, margin {margin}%)")

    # 結果保存
    today = datetime.now().strftime("%Y-%m-%d")
    suffix = f"_{args.output_suffix}" if args.output_suffix else ""
    json_path = RESULTS_DIR / f"scored_{today}{suffix}.json"
    md_path = RESULTS_DIR / f"shortlist_{today}{suffix}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)
    logger.info(f"スコア保存: {json_path}")

    md = generate_shortlist_md(scored)
    md_path.write_text(md, encoding="utf-8")
    logger.info(f"ショートリスト保存: {md_path}")

    # サマリー
    cat_counts: dict[str, int] = {}
    for s in scored:
        cat_counts[s["category"]] = cat_counts.get(s["category"], 0) + 1
    logger.info("=== サマリー ===")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {cat}: {n} 件")

    viable = [s for s in scored if s["category"] == "viable"]
    if viable:
        logger.info("\nTop 5 viable:")
        for s in sorted(viable, key=lambda x: -x.get("total", 0))[:5]:
            logger.info(f"  [{s['total']}/60] {s['title'][:60]} → "
                        f"原価¥{s.get('estimated_unit_cost_jpy', 0):,} / "
                        f"小売¥{s.get('estimated_retail_jpy', 0):,} / "
                        f"粗利{s.get('estimated_margin_pct', 0)}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
