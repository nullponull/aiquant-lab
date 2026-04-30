"""週次 top picks レポート + ALERT 検出

毎週月曜 06:00 実行。今週の top 5 候補をレポート化し、
品質スコア 75 以上の「即弁理士確認すべき候補」が見つかったら
ALERT ファイルを生成する。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
ALERT_DIR = HERE / "ALERT"
ALERT_DIR.mkdir(exist_ok=True)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("weekly_picks")


def get_lawyer_inquiry_template(r: dict) -> str:
    """弁理士向け確認依頼テンプレ生成"""
    return f"""## 弁理士への確認依頼テンプレ ({r.get('patent_number', '')})

```
件名: 期限切れ特許の事業化前 権利クリア確認依頼

[弁理士事務所名] 御中

期限切れ特許の事業化を検討しており、以下の確認を依頼したく存じます。

【対象特許】
特許番号: {r.get('patent_number', '')}
タイトル: {r.get('title', '')}
公開日: {r.get('publication_date', '')}
出願人: {r.get('assignee', '')}

【確認依頼事項】
1. 当該特許権の現在のステータス (権利消滅・期間満了・年金未納)
2. 同じ発明者/出願人による関連特許 (改良発明・分割出願) の有無
3. 同じ製品形状・名称の意匠権・商標権の登録有無
4. 米国・中国の対応特許の有無
5. 当該技術領域で第三者の特許訴訟が行われた事例の有無

【背景】
当社は J-PlatPat および AI スコアリングで予備調査を行い、
権利消滅していると認識しています。
量産・販売に進む前に、専門家のお墨付きを得たい状況です。

【製品概要】
- 推定構造: {r.get('product_summary', '')}
- 想定原価: ¥{r.get('estimated_unit_cost_jpy', 0):,}
- 想定小売: ¥{r.get('estimated_retail_jpy', 0):,}

【希望】
- 1 件あたりの調査見積もり
- 想定 5-10 件 (上記とは別の特許含む)
- 報告書形式 (法的判断の明示)

ご対応の可否、ご見積もりをお願いいたします。
```
"""


def main():
    # all_viable.json を読み込み
    json_in = RESULTS_DIR / "all_viable.json"
    if not json_in.exists():
        logger.warning("all_viable.json なし、aggregate_candidates.py を先に実行してください")
        return 1

    viable = json.load(open(json_in, encoding="utf-8"))
    if not viable:
        logger.info("viable 候補なし")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    week_label = datetime.now().strftime("%Y-W%V")

    # Top 5 ピック
    top5 = viable[:5]

    # ALERT 候補 (品質スコア 75+)
    excellent = [r for r in viable if r.get("_quality_score", 0) >= 75]

    # 週次レポート生成
    md_lines = []
    md_lines.append(f"# 週次 Top Picks ({today}, {week_label})")
    md_lines.append("")
    md_lines.append(f"累積 viable: {len(viable)} 件、本週の Top 5 を選定")
    md_lines.append("")

    # ALERT セクション (最上部)
    if excellent:
        md_lines.append("## ⚡ ALERT: 即弁理士確認推奨候補")
        md_lines.append("")
        md_lines.append(f"**品質スコア 75 以上の候補が {len(excellent)} 件あります。即アクション推奨。**")
        md_lines.append("")
        for r in excellent[:3]:
            md_lines.append(f"### 🌟 [{r['_quality_score']:.1f}/100] {r.get('title', '')}")
            md_lines.append(f"- 特許番号: `{r.get('patent_number', '')}`")
            md_lines.append(f"- 推定粗利: {r.get('estimated_margin_pct', 0)}%")
            md_lines.append(f"- 出願人: {r.get('assignee', '')}")
            md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    # Top 5 詳細
    md_lines.append("## 今週の Top 5")
    md_lines.append("")
    for i, r in enumerate(top5, 1):
        md_lines.append(f"### {i}. [{r.get('_quality_score', 0):.1f}/100] {r.get('title', '')}")
        md_lines.append("")
        md_lines.append(f"- **特許番号**: `{r.get('patent_number', '')}`")
        md_lines.append(f"- **公開日**: {r.get('publication_date', '')}")
        md_lines.append(f"- **出願人**: {r.get('assignee', '')}")
        md_lines.append(f"- **Claude スコア**: {r.get('total', 0)}/60")
        md_lines.append(f"- **推定原価/小売/粗利**: ¥{r.get('estimated_unit_cost_jpy', 0):,} → ¥{r.get('estimated_retail_jpy', 0):,} ({r.get('estimated_margin_pct', 0)}%)")
        md_lines.append(f"- **検索キーワード**: `{r.get('search_keyword', '')}`")
        md_lines.append(f"- **最大リスク**: {r.get('main_risk', '')}")
        md_lines.append(f"- **判定**: {r.get('verdict', '')}")
        md_lines.append(f"- **推奨**: {r.get('_recommendation', '')}")
        md_lines.append("")

    # 推奨アクション
    md_lines.append("## 推奨アクション")
    md_lines.append("")
    if excellent:
        md_lines.append(f"1. **EXCELLENT 候補 {len(excellent)} 件を弁理士へ送付** (今週中)")
        md_lines.append(f"   - 確認費用: ¥{30000 * min(len(excellent), 5):,}-{90000 * min(len(excellent), 5):,}")
        md_lines.append(f"   - 期間: 1-2 週間")
        md_lines.append("")
    else:
        md_lines.append("1. **現状の Top 5 を観察、別カテゴリのキーワード追加**")
        md_lines.append("")
    md_lines.append("2. **本週も patent-mine 自動継続** (毎日 22:00)")
    md_lines.append("3. **新着候補は all_viable.md に自動追加**")
    md_lines.append("")

    # 弁理士テンプレ
    if excellent:
        md_lines.append("---")
        md_lines.append("")
        md_lines.append("## 弁理士向けテンプレート (Top 候補用)")
        md_lines.append("")
        md_lines.append(get_lawyer_inquiry_template(excellent[0]))
        md_lines.append("")

    out_path = RESULTS_DIR / f"weekly_top_picks_{today}.md"
    out_path.write_text("\n".join(md_lines), encoding="utf-8")
    logger.info(f"週次レポート保存: {out_path}")

    # ALERT ファイル生成
    if excellent:
        alert_path = ALERT_DIR / f"ALERT_{today}_excellent_candidates.md"
        alert_lines = [
            f"# ⚡ ALERT: EXCELLENT 候補発見 ({today})",
            "",
            f"品質スコア 75 以上の候補が **{len(excellent)} 件** 見つかりました。",
            "",
            "## 即実行すべきアクション",
            "",
            "1. 該当特許を J-PlatPat で本文確認",
            "2. 弁理士に確認依頼 (テンプレは weekly_top_picks_*.md 参照)",
            "3. Amazon JP / 楽天で類似商品の競合状況確認",
            "4. 結論を 1 週間以内に出す",
            "",
            "---",
            "",
            "## 該当候補",
            "",
        ]
        for r in excellent:
            alert_lines.append(f"### [{r.get('_quality_score', 0):.1f}/100] {r.get('title', '')}")
            alert_lines.append(f"- 特許: `{r.get('patent_number', '')}`")
            alert_lines.append(f"- 推定粗利: {r.get('estimated_margin_pct', 0)}%")
            alert_lines.append(f"- 出願人: {r.get('assignee', '')}")
            alert_lines.append("")
        alert_path.write_text("\n".join(alert_lines), encoding="utf-8")
        logger.info(f"⚡ ALERT 生成: {alert_path}")

    # サマリー
    logger.info("=== 週次 Top Picks サマリー ===")
    logger.info(f"  累積 viable: {len(viable)}")
    logger.info(f"  EXCELLENT (≥75): {len(excellent)}")
    if excellent:
        logger.info(f"  ⚡ ALERT 候補:")
        for r in excellent[:3]:
            logger.info(f"    - {r.get('patent_number', '')} {r.get('title', '')[:50]} (品質 {r.get('_quality_score', 0):.1f})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
