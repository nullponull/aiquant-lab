"""候補特許の市場参入調査レポートを生成

入力: viable な特許情報 + 競合調査データ (Amazon JP 等)
出力: 構造化された市場参入レポート (markdown)

レポート内容:
1. 製品仕様の整理
2. 競合分析 (実取得データ + Claude 知識)
3. 試作方法
4. OEM/製造選択肢
5. 販売チャネル
6. 投資見積もり (Phase 0-4)
7. 想定リターン
8. リスクと判断基準
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("market_entry")

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"


RESEARCH_SYSTEM = """
あなたは中小企業の新規事業開発コンサルタントです。
期限切れ特許を活用した小規模製造業のスタートを支援します。

これは投資助言ではなく、製品開発の市場参入調査タスクです。
具体的かつ実務的な答えを提供してください。

評価する観点:
- 試作方法 (3D プリント、試作業者)
- 国内 OEM (小ロット製造可能な業者の例)
- 海外 OEM (Alibaba、Made-in-China のサプライヤー検索キーワード)
- 販売チャネル (Amazon、楽天、Pinkoi、ペット系専門 EC、自社 EC)
- 想定 MOQ (Minimum Order Quantity) と単価
- マーケティング差別化のポイント
- 必要な認証/規制 (ペット用品なら PSE、食品衛生法等)
- 想定総投資額 (試作〜販売開始)
- 想定月商レンジ
- 主要リスク

形式: markdown で整理されたレポート。各セクションに具体的な数値・固有名詞を含める。
"""


def generate_report(
    patent: dict,
    competitor_data: dict,
    model: str = "haiku",
) -> str:
    """市場参入レポートを Claude で生成"""
    if not shutil.which("claude"):
        return "Claude CLI not available"

    # 競合データはサマリ化して短く渡す（フル JSON は重い）
    comp_summary = json.dumps({
        "price_distribution": competitor_data.get("price_distribution", {}),
        "differentiation_observations": competitor_data.get("differentiation_observations", {}),
        "customer_pain_points_inferred": competitor_data.get("customer_pain_points_inferred", []),
        "top_competitors": [
            {"title": c["title"][:80], "price_jpy": c["price_jpy"], "type": c.get("type", "")}
            for c in competitor_data.get("competitors", [])[:6]
        ],
    }, ensure_ascii=False, indent=2)

    user_prompt = f"""特許: {patent.get('patent_number')} / {patent.get('title')}
推定原価¥{patent.get('estimated_unit_cost_jpy', 0):,} / 小売¥{patent.get('estimated_retail_jpy', 0):,} / 粗利{patent.get('estimated_margin_pct', 0)}%

競合 (Amazon JP):
{comp_summary}

以下の市場参入レポートを markdown で。具体的固有名詞・数値・URL 入り、合計 2000 字程度。

## 1. 製品仕様の整理
## 2. 競合分析（差別化要素含む）
## 3. 試作フェーズ（3Dプリント業者・試作費・期間）
## 4. 量産フェーズ（国内/海外 OEM・MOQ・認証）
## 5. 販売チャネル（Amazon/楽天/自社EC/専門EC）
## 6. 投資見積もりと回収計画（年商 500-2000 万なら）
## 7. 主要リスクと撤退基準
## 8. 今すぐやれる 5 つのアクション

冷静・実務的に。各セクション 200-300 字。
"""

    cmd = [
        "claude",
        "-p", user_prompt,
        "--model", model,
        "--output-format", "json",
        "--append-system-prompt", RESEARCH_SYSTEM,
        "--no-session-persistence",
        "--disable-slash-commands",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return "Claude timeout (600s exceeded)"

    if r.returncode != 0:
        return f"Claude error: exit {r.returncode}"

    try:
        outer = json.loads(r.stdout)
        return outer.get("result", "(empty)")
    except json.JSONDecodeError:
        return f"Parse error: {r.stdout[:300]}"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("scored_json", help="run_jplatpat_daily の出力 scored_*.json")
    parser.add_argument("--patent-number", type=str, required=True,
                        help="対象特許番号 (例: 実登3101582)")
    parser.add_argument("--competitor-json", type=str, default=None,
                        help="競合データ JSON (オプション)")
    args = parser.parse_args()

    # Patent 取得
    scored = json.load(open(args.scored_json, encoding="utf-8"))
    patent = next((p for p in scored if p.get("patent_number") == args.patent_number), None)
    if not patent:
        logger.error(f"特許 {args.patent_number} が見つかりません")
        return 1

    # 競合データ
    if args.competitor_json:
        competitor_data = json.load(open(args.competitor_json, encoding="utf-8"))
    else:
        competitor_data = {"note": "競合データなし。Claude の業界知識で補完。"}

    logger.info(f"=== 市場参入調査 for {args.patent_number}: {patent['title']} ===")
    logger.info("Claude にレポート生成を依頼中... (1-3 分かかります)")
    report = generate_report(patent, competitor_data)

    # 出力
    today = datetime.now().strftime("%Y-%m-%d")
    safe_num = args.patent_number.replace("/", "_").replace(" ", "_")
    out_path = RESULTS_DIR / f"market_entry_{today}_{safe_num}.md"
    full_md = f"""# 市場参入調査レポート: {patent['title']}

> 特許番号: `{args.patent_number}`
> 生成: {datetime.now().isoformat(timespec='seconds')}
> 対象者: 企業事業として実装するエンジニア・起業家

---

## 元データ

- **タイトル**: {patent['title']}
- **公開日**: {patent.get('publication_date', '')}
- **出願人**: {patent.get('assignee', '')}
- **Claude 評価 (Phase 0)**:
  - スコア合計: {patent.get('total', 0)}/60
  - カテゴリ: {patent.get('category', '')}
  - 推定原価: ¥{patent.get('estimated_unit_cost_jpy', 0):,}
  - 推定小売: ¥{patent.get('estimated_retail_jpy', 0):,}
  - 推定粗利: {patent.get('estimated_margin_pct', 0)}%

---

{report}

---

## 免責事項

本レポートは AI による市場参入調査の参考情報であり、投資助言・経営助言ではありません。
実際の事業判断には、弁理士・税理士・経営コンサル等の専門家への相談が必要です。
"""
    out_path.write_text(full_md, encoding="utf-8")
    logger.info(f"レポート保存: {out_path}")
    print(f"\n{'='*60}")
    print(f"レポート: {out_path}")
    print(f"{'='*60}")
    print(report[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
