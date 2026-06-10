"""日次 digest を markdown で生成"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable


CATEGORY_LABEL = {
    "sku5_scam": "SKU 5 詐欺解剖DB候補",
    "sku5_credible": "SKU 5 対極事例 / 信頼できる投資論",
    "series_material": "連載素材",
    "regime_change": "市場構造変化",
    "failure_case": "失敗事例",
    "tool_release": "新ツール",
    "competitor": "類似商材ローンチ",
    "discard": "破棄候補",
}


def generate_digest(date: str, all_items: list[dict], filtered: list[dict]) -> str:
    """digest.md の本文を生成

    各アイテム形式:
    {
        "item": {... Item.to_dict() ...},
        "classification": {"score": int, "category": str, "reason": str}
    }
    """
    lines: list[str] = []
    lines.append(f"# {date} リサーチダイジェスト")
    lines.append("")
    lines.append(f"- 総取得: **{len(all_items)} 件**")
    lines.append(f"- スコア 6+ 通過: **{len(filtered)} 件**")
    lines.append(f"- 生成: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    # カテゴリ別集計
    category_counts: dict[str, int] = {}
    for entry in filtered:
        cat = entry["classification"]["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
    if category_counts:
        lines.append("## カテゴリ別件数")
        lines.append("")
        for cat, n in sorted(category_counts.items(), key=lambda x: -x[1]):
            label = CATEGORY_LABEL.get(cat, cat)
            lines.append(f"- {label}: {n} 件")
        lines.append("")

    # スコア順上位
    sorted_entries = sorted(
        filtered, key=lambda x: x["classification"]["score"], reverse=True
    )
    lines.append("## トップ 20")
    lines.append("")
    for i, entry in enumerate(sorted_entries[:20], 1):
        item = entry["item"]
        cls = entry["classification"]
        cat_label = CATEGORY_LABEL.get(cls["category"], cls["category"])
        lines.append(f"### {i}. [{cls['score']}/10 {cat_label}] {item['title'][:80]}")
        lines.append("")
        lines.append(f"- **出典**: `{item['source']}` ({item['source_type']})")
        if item.get("author"):
            lines.append(f"- **著者**: {item['author']}")
        if item.get("published_at"):
            lines.append(f"- **公開**: {item['published_at']}")
        lines.append(f"- **URL**: {item['url']}")
        if cls.get("reason"):
            lines.append(f"- **判定理由**: {cls['reason']}")
        body_excerpt = (item.get("body") or "").replace("\n", " ")[:150]
        if body_excerpt:
            lines.append(f"- **抜粋**: {body_excerpt}...")
        lines.append("")

    # 全アイテム一覧 (折りたたみ)
    lines.append("## 全フィルタ通過アイテム")
    lines.append("")
    lines.append("<details><summary>展開</summary>")
    lines.append("")
    for entry in sorted_entries:
        item = entry["item"]
        cls = entry["classification"]
        lines.append(f"- [{cls['score']}/10 {cls['category']}] [{item['title'][:80]}]({item['url']})")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    return "\n".join(lines)
