"""週次 top picks v2: PDCA 統合版

毎週月曜 06:00 実行:
1. aggregate_candidates 最新化
2. Top 5 候補に PDCA を実行 (まだ実行していない候補のみ)
3. PDCA 結果を統合して週次レポート生成
4. **GO 判定の候補があれば** ALERT 生成 (品質スコア単独では ALERT しない)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pdca_evaluator import run_pdca_for_patent

RESULTS_DIR = HERE / "results"
PDCA_DIR = HERE / "pdca_results"
ALERT_DIR = HERE / "ALERT"
ALERT_DIR.mkdir(exist_ok=True)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("weekly_v2")


def load_pdca_result(patent_number: str) -> dict | None:
    safe_num = patent_number.replace("/", "_").replace(" ", "_")
    p = PDCA_DIR / f"pdca_{safe_num}.json"
    if not p.exists():
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def main():
    json_in = RESULTS_DIR / "all_viable.json"
    if not json_in.exists():
        logger.error("all_viable.json なし")
        return 1

    viable = json.load(open(json_in, encoding="utf-8"))
    if not viable:
        logger.info("viable 候補なし")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")

    # Top 5 で PDCA 未実施のものに対して実行
    top_n = viable[:5]
    logger.info(f"=== Top 5 候補に PDCA 実行 ===")
    for patent in top_n:
        num = patent.get("patent_number")
        if not num:
            continue
        existing = load_pdca_result(num)
        if existing:
            logger.info(f"  既存 PDCA を使用: {num}")
            continue
        try:
            run_pdca_for_patent(patent)
        except Exception as e:
            logger.warning(f"  例外: {num}: {e}")

    # PDCA 結果を統合
    enriched: list[dict] = []
    for patent in viable:
        num = patent.get("patent_number")
        pdca = load_pdca_result(num) if num else None
        patent_copy = dict(patent)
        if pdca:
            verdict = pdca.get("pdca_verdict", {})
            patent_copy["pdca_verdict"] = verdict.get("verdict", "?")
            patent_copy["pdca_real_bom"] = verdict.get("real_bom_jpy")
            patent_copy["pdca_recommended_retail"] = verdict.get("recommended_retail_jpy")
            patent_copy["pdca_real_margin"] = verdict.get("estimated_margin_pct")
            patent_copy["pdca_price_advantage"] = verdict.get("price_advantage_score")
            patent_copy["pdca_differentiation"] = verdict.get("differentiation_score")
            patent_copy["pdca_summary"] = verdict.get("summary", "")
            patent_copy["pdca_concerns"] = verdict.get("main_concerns", [])
            patent_copy["pdca_actions"] = verdict.get("next_actions", [])
        enriched.append(patent_copy)

    # GO 判定の候補抽出
    go_candidates = [p for p in enriched if p.get("pdca_verdict") == "GO"]

    # 週次レポート生成
    md_lines = []
    md_lines.append(f"# 週次 Top Picks PDCA 統合版 ({today})")
    md_lines.append("")
    md_lines.append(f"累積 viable: {len(enriched)} 件")
    md_lines.append(f"PDCA 完了: {sum(1 for p in enriched if p.get('pdca_verdict'))} 件")
    md_lines.append(f"**GO 判定: {len(go_candidates)} 件**")
    md_lines.append("")

    # ALERT セクション (GO 判定のみ)
    if go_candidates:
        md_lines.append("## ⚡ ALERT: GO 判定候補")
        md_lines.append("")
        md_lines.append(f"**PDCA フル評価で GO 判定の候補が {len(go_candidates)} 件あります。即弁理士確認推奨。**")
        md_lines.append("")
        for p in go_candidates:
            md_lines.append(f"### 🌟 {p.get('title', '')}")
            md_lines.append(f"- 特許番号: `{p.get('patent_number', '')}`")
            md_lines.append(f"- **判定**: GO")
            md_lines.append(f"- 実 BOM: ¥{p.get('pdca_real_bom', 0):,}")
            md_lines.append(f"- 推奨小売: ¥{p.get('pdca_recommended_retail', 0):,}")
            md_lines.append(f"- 実粗利: {p.get('pdca_real_margin', 0)}%")
            md_lines.append(f"- 価格優位スコア: {p.get('pdca_price_advantage', 0)}/10")
            md_lines.append(f"- 差別化スコア: {p.get('pdca_differentiation', 0)}/10")
            md_lines.append(f"- **結論**: {p.get('pdca_summary', '')}")
            md_lines.append("")
            md_lines.append("**次のアクション**:")
            for a in p.get('pdca_actions', []):
                md_lines.append(f"- {a}")
            md_lines.append("")
        md_lines.append("---")
        md_lines.append("")
    else:
        md_lines.append("## 今週の状況")
        md_lines.append("")
        md_lines.append("**GO 判定の候補はまだ見つかっていません。**")
        md_lines.append("patent-mine の自動運用を継続し、新候補が現れるのを待ちます。")
        md_lines.append("")

    # Top 5 の PDCA サマリー (GO 以外も含む)
    md_lines.append("## Top 5 PDCA 結果")
    md_lines.append("")
    md_lines.append("| 順位 | 品質 | PDCA | 特許 | 実 BOM | 推奨小売 | 粗利 | 価格優位 | 差別化 |")
    md_lines.append("|------|------|------|------|--------|--------|------|--------|------|")
    for i, p in enumerate(enriched[:5], 1):
        verdict = p.get('pdca_verdict', '?')
        verdict_icon = {"GO": "🌟 GO", "MAYBE": "⚠️ MAYBE", "NO-GO": "❌ NO-GO"}.get(verdict, verdict)
        md_lines.append(
            f"| {i} | {p.get('_quality_score', 0):.1f} | {verdict_icon} | "
            f"`{p.get('patent_number', '')}` {p.get('title', '')[:25]} | "
            f"¥{p.get('pdca_real_bom', 0):,} | "
            f"¥{p.get('pdca_recommended_retail', 0):,} | "
            f"{p.get('pdca_real_margin', 0)}% | "
            f"{p.get('pdca_price_advantage', '?')}/10 | "
            f"{p.get('pdca_differentiation', '?')}/10 |"
        )
    md_lines.append("")

    # 詳細 (Top 3)
    md_lines.append("## Top 3 詳細")
    md_lines.append("")
    for i, p in enumerate(enriched[:3], 1):
        md_lines.append(f"### {i}. [{p.get('pdca_verdict', '?')}] {p.get('title', '')}")
        md_lines.append("")
        md_lines.append(f"- 特許番号: `{p.get('patent_number', '')}`")
        md_lines.append(f"- 出願人: {p.get('assignee', '')}")
        md_lines.append(f"- 公開日: {p.get('publication_date', '')}")
        md_lines.append(f"- Claude 初期スコア: {p.get('total', 0)}/60 (品質 {p.get('_quality_score', 0):.1f})")
        if p.get('pdca_verdict'):
            md_lines.append(f"- **PDCA 判定**: {p.get('pdca_verdict')}")
            md_lines.append(f"- 実 BOM (本文ベース): ¥{p.get('pdca_real_bom', 0):,}")
            md_lines.append(f"- 推奨小売: ¥{p.get('pdca_recommended_retail', 0):,}")
            md_lines.append(f"- 実粗利: {p.get('pdca_real_margin', 0)}%")
            md_lines.append(f"- 結論: {p.get('pdca_summary', '')}")
            md_lines.append("- 主な懸念:")
            for c in p.get('pdca_concerns', [])[:3]:
                md_lines.append(f"  - {c}")
        else:
            md_lines.append(f"- PDCA 未実行")
        md_lines.append("")

    out_path = RESULTS_DIR / f"weekly_pdca_{today}.md"
    out_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info(f"週次 PDCA レポート: {out_path}")

    # ALERT ファイル (GO 判定があるとき)
    if go_candidates:
        alert_path = ALERT_DIR / f"GO_ALERT_{today}.md"
        alert_lines = [
            f"# ⚡⚡⚡ GO ALERT: 事業化推奨候補発見 ({today})",
            "",
            f"**PDCA フル評価で GO 判定の候補が {len(go_candidates)} 件**。",
            "",
            "## 即実行すべきアクション",
            "",
            "1. 該当特許の弁理士確認 (¥30K-90K, 1-2 週間)",
            "2. 試作見積もり取得 (DMM.make, Spaceship 9 等)",
            "3. Alibaba/Made-in-China での OEM サンプル発注",
            "4. Makuake クラウドファンディング検討",
            "",
            "## 該当候補",
            "",
        ]
        for p in go_candidates:
            alert_lines.append(f"### {p.get('title', '')}")
            alert_lines.append(f"- 特許: `{p.get('patent_number', '')}`")
            alert_lines.append(f"- BOM ¥{p.get('pdca_real_bom', 0):,} → 小売 ¥{p.get('pdca_recommended_retail', 0):,} (粗利 {p.get('pdca_real_margin', 0)}%)")
            alert_lines.append(f"- 価格優位 {p.get('pdca_price_advantage', '?')}/10, 差別化 {p.get('pdca_differentiation', '?')}/10")
            alert_lines.append(f"- 結論: {p.get('pdca_summary', '')}")
            alert_lines.append("")
        alert_path.write_text("\n".join(alert_lines), encoding="utf-8")
        logger.info(f"⚡⚡⚡ GO ALERT: {alert_path}")

    # サマリー
    logger.info("=== サマリー ===")
    logger.info(f"  累積 viable: {len(enriched)}")
    logger.info(f"  PDCA 完了: {sum(1 for p in enriched if p.get('pdca_verdict'))}")
    logger.info(f"  GO: {len(go_candidates)}")
    logger.info(f"  MAYBE: {sum(1 for p in enriched if p.get('pdca_verdict') == 'MAYBE')}")
    logger.info(f"  NO-GO: {sum(1 for p in enriched if p.get('pdca_verdict') == 'NO-GO')}")
    if go_candidates:
        logger.info("  ⚡⚡⚡ GO 候補:")
        for p in go_candidates:
            logger.info(f"    - {p.get('patent_number')} {p.get('title', '')[:50]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
