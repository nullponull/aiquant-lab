"""全 viable 候補を集約して累積ランキングを生成

毎日実行 (lightweight)。results/all_viable.md と all_viable.json を更新。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aggregator")


def load_all_scored() -> list[dict]:
    """results 配下の全 scored_*.json を読み込む"""
    all_records: list[dict] = []
    for f in sorted(RESULTS_DIR.glob("scored_*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
            for r in data:
                r["_source_file"] = f.name
            all_records.extend(data)
        except Exception as e:
            logger.warning(f"  skip {f.name}: {e}")
    return all_records


def dedupe_by_patent_number(records: list[dict]) -> list[dict]:
    """同一特許番号の重複を排除（最新のスコアを採用）"""
    seen: dict[str, dict] = {}
    for r in records:
        num = r.get("patent_number", "")
        if not num:
            continue
        # _source_file の日付が新しい方を残す
        if num not in seen or r.get("_source_file", "") > seen[num].get("_source_file", ""):
            seen[num] = r
    return list(seen.values())


def quality_score(r: dict) -> float:
    """事業候補としての総合スコア (0-100)

    Claude total (60点満点) を 60% 配分、追加ボーナスを 40% 配分。
    """
    base = r.get("total", 0) / 60 * 60  # 0-60

    # ボーナス要素
    bonus = 0

    # 推定粗利 50%以上
    margin = r.get("estimated_margin_pct", 0)
    if margin >= 70:
        bonus += 15
    elif margin >= 60:
        bonus += 10
    elif margin >= 50:
        bonus += 5

    # 出願人が個人 or 小規模
    assignee = (r.get("assignee", "") or "").strip()
    if assignee == "個人" or assignee == "" or "個人" in assignee:
        bonus += 10
    elif "有限会社" in assignee or "個人事業" in assignee:
        bonus += 7

    # 単価レンジ（売れる帯）
    retail = r.get("estimated_retail_jpy", 0)
    if 1500 <= retail <= 5000:  # スイートスポット
        bonus += 10
    elif 5000 < retail <= 10000:
        bonus += 5

    # 構造シンプル (simplicity 8+)
    simplicity = r.get("scores", {}).get("simplicity", 0)
    if simplicity >= 8:
        bonus += 5

    return base + bonus


def categorize_recommendation(r: dict, total_quality: float) -> str:
    """「これは良い」「微妙」のラベル付け"""
    if total_quality >= 75:
        return "🌟 EXCELLENT (即弁理士確認推奨)"
    elif total_quality >= 65:
        return "✓ GOOD (週次ピックアップ候補)"
    elif total_quality >= 55:
        return "○ FAIR (条件次第で検討)"
    else:
        return "△ MARGINAL (見送り推奨)"


def main():
    logger.info("=== 候補集約開始 ===")
    all_records = load_all_scored()
    logger.info(f"全レコード: {len(all_records)} 件")

    deduped = dedupe_by_patent_number(all_records)
    logger.info(f"重複排除後: {len(deduped)} 件")

    # viable のみ
    viable = [r for r in deduped if r.get("category") == "viable"]
    logger.info(f"viable: {len(viable)} 件")

    if not viable:
        logger.info("viable 候補なし、終了")
        return 0

    # 品質スコア計算
    for r in viable:
        r["_quality_score"] = quality_score(r)
        r["_recommendation"] = categorize_recommendation(r, r["_quality_score"])

    viable.sort(key=lambda x: -x["_quality_score"])

    # JSON 保存
    json_out = RESULTS_DIR / "all_viable.json"
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(viable, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON 保存: {json_out}")

    # markdown 保存
    today = datetime.now().strftime("%Y-%m-%d")
    md_lines = []
    md_lines.append(f"# 全 viable 候補ランキング (累積、最終更新 {today})")
    md_lines.append("")
    md_lines.append(f"対象: 累積 {len(viable)} 件 (重複排除済)")
    md_lines.append("")
    md_lines.append("## 推奨ラベル別件数")
    md_lines.append("")
    label_counts: dict[str, int] = {}
    for r in viable:
        label_counts[r["_recommendation"]] = label_counts.get(r["_recommendation"], 0) + 1
    for label, n in sorted(label_counts.items(), key=lambda x: -x[1]):
        md_lines.append(f"- {label}: {n} 件")
    md_lines.append("")

    # Top 20 詳細
    md_lines.append("## TOP 20 (品質スコア降順)")
    md_lines.append("")
    md_lines.append("| 順位 | 品質 | スコア | 特許 | 推定原価 | 推定小売 | 粗利 | ラベル |")
    md_lines.append("|------|------|------|------|--------|--------|------|------|")
    for i, r in enumerate(viable[:20], 1):
        md_lines.append(
            f"| {i} | {r['_quality_score']:.1f} | {r.get('total', 0)}/60 | "
            f"`{r.get('patent_number', '')}` {r.get('title', '')[:30]} | "
            f"¥{r.get('estimated_unit_cost_jpy', 0):,} | "
            f"¥{r.get('estimated_retail_jpy', 0):,} | "
            f"{r.get('estimated_margin_pct', 0)}% | "
            f"{r['_recommendation']} |"
        )
    md_lines.append("")

    # Top 5 詳細プロファイル
    md_lines.append("## TOP 5 詳細プロファイル")
    md_lines.append("")
    for i, r in enumerate(viable[:5], 1):
        md_lines.append(f"### {i}. [{r['_quality_score']:.1f}/100] {r.get('title', '')}")
        md_lines.append("")
        md_lines.append(f"- **特許番号**: `{r.get('patent_number', '')}`")
        md_lines.append(f"- **公開日**: {r.get('publication_date', '')}")
        md_lines.append(f"- **出願人**: {r.get('assignee', '')}")
        md_lines.append(f"- **製品サマリー**: {r.get('product_summary', '')}")
        md_lines.append(f"- **推定原価**: ¥{r.get('estimated_unit_cost_jpy', 0):,}")
        md_lines.append(f"- **推定小売**: ¥{r.get('estimated_retail_jpy', 0):,}")
        md_lines.append(f"- **推定粗利**: {r.get('estimated_margin_pct', 0)}%")
        md_lines.append(f"- **検索キーワード**: `{r.get('search_keyword', '')}`")
        md_lines.append(f"- **最大リスク**: {r.get('main_risk', '')}")
        md_lines.append(f"- **判定**: {r.get('verdict', '')}")
        md_lines.append(f"- **推奨アクション**: {r['_recommendation']}")
        md_lines.append("")

    md_out = RESULTS_DIR / "all_viable.md"
    md_out.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info(f"markdown 保存: {md_out}")

    # 統計サマリー
    excellent = sum(1 for r in viable if r["_quality_score"] >= 75)
    good = sum(1 for r in viable if 65 <= r["_quality_score"] < 75)
    logger.info(f"=== サマリー ===")
    logger.info(f"  EXCELLENT (≥75): {excellent} 件")
    logger.info(f"  GOOD (65-75):    {good} 件")
    if excellent > 0:
        logger.info(f"  ⚡ ALERT: 即弁理士確認推奨候補が {excellent} 件あります")

    return 0


if __name__ == "__main__":
    sys.exit(main())
