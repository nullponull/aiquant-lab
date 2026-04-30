"""Phase 0 パイロット: サンプル特許 10 件で pipeline 動作確認 + shortlist 生成

実行:
    uv run python automation/patent_mine/run_pilot.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from scorer import score_patent

DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(exist_ok=True)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("patent_mine_pilot")


def load_sample_patents() -> list[dict]:
    f = DATA_DIR / "sample_patents.json"
    return json.load(open(f, encoding="utf-8"))["patents"]


def score_all(patents: list[dict]) -> list[dict]:
    scored: list[dict] = []
    for i, p in enumerate(patents, 1):
        logger.info(f"  [{i}/{len(patents)}] {p['patent_number']}: {p['title'][:50]}")
        result = score_patent(p)
        if "_error" in result:
            logger.warning(f"    ✗ error: {result['_error']}")
            continue
        result["patent_number"] = p["patent_number"]
        result["title"] = p["title"]
        result["category_hint"] = p.get("category_hint", "")
        result["publication_date"] = p.get("publication_date", "")
        result["assignee"] = p.get("assignee", "")
        scored.append(result)
        logger.info(f"    → {result.get('category')} (total {result.get('total')}/60, "
                    f"margin {result.get('estimated_margin_pct')}%)")
    return scored


def generate_shortlist_md(scored: list[dict]) -> str:
    """ショートリスト markdown 生成"""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"# 期限切れ特許 事業化候補 ショートリスト ({today})")
    lines.append("")
    lines.append(f"対象件数: {len(scored)}")
    lines.append(f"生成: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    # カテゴリ別集計
    cat_counts: dict[str, int] = {}
    for s in scored:
        cat_counts[s["category"]] = cat_counts.get(s["category"], 0) + 1
    lines.append("## カテゴリ別件数")
    lines.append("")
    for cat, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- **{cat}**: {n} 件")
    lines.append("")

    # viable のみ抽出
    viable = [s for s in scored if s["category"] == "viable"]
    viable.sort(key=lambda s: -s.get("total", 0))

    if viable:
        lines.append("## 事業化候補 (viable, 合計スコア順)")
        lines.append("")
        for i, s in enumerate(viable, 1):
            lines.append(f"### {i}. [{s['total']}/60] {s['title']} (`{s['patent_number']}`)")
            lines.append("")
            lines.append(f"- **製品サマリー**: {s.get('product_summary', '')}")
            lines.append(f"- **推定原価**: ¥{s.get('estimated_unit_cost_jpy', 0):,}")
            lines.append(f"- **推定小売**: ¥{s.get('estimated_retail_jpy', 0):,}")
            lines.append(f"- **推定粗利**: {s.get('estimated_margin_pct', 0)}%")
            lines.append(f"- **公開日**: {s['publication_date']}")
            lines.append(f"- **出願人**: {s['assignee']}")
            lines.append(f"- **最大リスク**: {s.get('main_risk', '')}")
            lines.append(f"- **判定**: {s.get('verdict', '')}")
            lines.append("")
            scores = s.get("scores", {})
            lines.append("**6 軸スコア**:")
            lines.append(f"- シンプルさ: {scores.get('simplicity', 0)}/10")
            lines.append(f"- 差別化度: {scores.get('originality', 0)}/10")
            lines.append(f"- 市場需要: {scores.get('demand', 0)}/10")
            lines.append(f"- 製造コスト適性: {scores.get('cost_feasibility', 0)}/10")
            lines.append(f"- 権利クリア容易さ: {scores.get('legal_clearance', 0)}/10")
            lines.append(f"- 小ロット適性: {scores.get('moq_compatibility', 0)}/10")
            lines.append("")

    # marginal も別セクション
    marginal = [s for s in scored if s["category"] == "marginal"]
    if marginal:
        lines.append("## 条件付き候補 (marginal)")
        lines.append("")
        for s in marginal:
            lines.append(f"- **{s['title']}** ({s['patent_number']}): "
                         f"total {s.get('total', 0)}/60 / {s.get('verdict', '')}")
        lines.append("")

    # skip 系
    skips = [s for s in scored if s["category"].startswith("skip")]
    if skips:
        lines.append("## スキップ判定 (skip 系)")
        lines.append("")
        for s in skips:
            lines.append(f"- ~~{s['title']}~~ (`{s['patent_number']}`): "
                         f"{s['category']} | {s.get('main_risk', '')}")
        lines.append("")

    # Phase 1 への進め方
    lines.append("## Phase 1 (法的クリア確認) への進め方")
    lines.append("")
    lines.append("以下の `viable` 候補について、弁理士に確認依頼を出す:")
    lines.append("")
    lines.append("1. **特許権の確認**:")
    lines.append("   - J-PlatPat の経過情報で「権利消滅」「期間満了」「年金未納」を確認")
    lines.append("   - 同じ発明者/出願人の関連特許を検索 (改良発明が現役の可能性)")
    lines.append("")
    lines.append("2. **意匠権の確認**:")
    lines.append("   - 形状が独特な場合、意匠登録されていないか J-PlatPat で確認")
    lines.append("")
    lines.append("3. **商標権の確認**:")
    lines.append("   - 商品名/ブランド名として使われていた場合、現在も登録されているか確認")
    lines.append("")
    lines.append("4. **米国・中国特許の有無**:")
    lines.append("   - 同じ発明が米国/中国で別途登録されている可能性 (Espacenet で確認)")
    lines.append("")
    lines.append("**弁理士見積もり目安**: 1 件あたり ¥10,000-30,000 (調査のみ、訴訟ではない)")
    lines.append("")

    return "\n".join(lines)


def main():
    logger.info("=== Patent Mine Pilot (Phase 0) ===")

    patents = load_sample_patents()
    logger.info(f"対象: {len(patents)} 件")

    scored = score_all(patents)
    if not scored:
        logger.error("スコアリング結果なし、終了")
        return 1

    # 結果保存
    today = datetime.now().strftime("%Y-%m-%d")
    json_path = RESULTS_DIR / f"scored_{today}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)
    logger.info(f"スコア保存: {json_path}")

    md = generate_shortlist_md(scored)
    md_path = RESULTS_DIR / f"shortlist_{today}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    logger.info(f"ショートリスト保存: {md_path}")

    # サマリー
    viable = [s for s in scored if s["category"] == "viable"]
    marginal = [s for s in scored if s["category"] == "marginal"]
    logger.info("=== サマリー ===")
    logger.info(f"  viable (事業化候補): {len(viable)} 件")
    logger.info(f"  marginal (条件付き): {len(marginal)} 件")
    logger.info(f"  skip 系: {len(scored) - len(viable) - len(marginal)} 件")

    if viable:
        logger.info("\nTOP 候補:")
        for s in sorted(viable, key=lambda x: -x.get("total", 0))[:3]:
            logger.info(f"  [{s['total']}/60] {s['title']} → {s.get('verdict', '')[:60]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
