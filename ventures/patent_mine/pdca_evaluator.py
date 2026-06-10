"""PDCA 完全評価器: 特許本文 + 競合データ → GO/MAYBE/NO-GO 判定"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# patent_text_fetcher と amazon_jp_search は system python3 経由で実行する
# (playwright が system に入っているため)

RESULTS_DIR = HERE / "results"
PDCA_DIR = HERE / "pdca_results"
PDCA_DIR.mkdir(exist_ok=True)

SYSTEM_PYTHON = "/usr/bin/python3"


def fetch_patent_text(patent_number: str, headless: bool = True) -> dict:
    """system python3 経由で patent_text_fetcher を呼ぶ"""
    bridge = f"""
import json, sys
sys.path.insert(0, '{HERE}')
from sources.patent_text_fetcher import fetch_patent_text
result = fetch_patent_text({json.dumps(patent_number)}, headless={headless})
print(json.dumps(result, ensure_ascii=False))
"""
    try:
        r = subprocess.run(
            [SYSTEM_PYTHON, "-c", bridge],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"_error": "patent_text_fetcher timeout"}
    if r.returncode != 0:
        return {"_error": f"exit {r.returncode}: {r.stderr[-200:]}"}
    last_json = ""
    for line in reversed(r.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            last_json = line
            break
    if not last_json:
        return {"_error": "no json output"}
    try:
        return json.loads(last_json)
    except json.JSONDecodeError as e:
        return {"_error": f"parse: {e}"}


def search_amazon_jp(query: str, max_results: int = 12, headless: bool = True) -> dict:
    """system python3 経由で amazon_jp_search を呼ぶ"""
    bridge = f"""
import json, sys
sys.path.insert(0, '{HERE}')
from sources.amazon_jp_search import search_amazon_jp
result = search_amazon_jp({json.dumps(query)}, max_results={max_results}, headless={headless})
print(json.dumps(result, ensure_ascii=False))
"""
    try:
        r = subprocess.run(
            [SYSTEM_PYTHON, "-c", bridge],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"_error": "amazon_jp_search timeout"}
    if r.returncode != 0:
        return {"_error": f"exit {r.returncode}: {r.stderr[-200:]}"}
    last_json = ""
    for line in reversed(r.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            last_json = line
            break
    if not last_json:
        return {"_error": "no json output"}
    try:
        return json.loads(last_json)
    except json.JSONDecodeError as e:
        return {"_error": f"parse: {e}"}


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pdca")


PDCA_SYSTEM = """
あなたは中小企業の事業評価アナリストです。
期限切れ特許 + 実競合データから、製造販売事業として GO/MAYBE/NO-GO を判定します。

これは投資助言ではなく、製品開発の事業性分析タスクです。
構造化された JSON で、根拠を含めて判定してください。

判定基準:
- **GO**: 価格優位性◎ + 構造シンプル + 飽和低 → 即弁理士確認
- **MAYBE**: 価格優位性○ or 一部制約あり → 慎重に検討
- **NO-GO**: 価格優位性なし or 構造複雑 or 飽和高 → 別候補へ

重要: 特許本文（要約・課題・解決手段）から実際の構造を読み取り、
そこから現実的な BOM (材料費合計) を見積もる。タイトルからの推測ではなく、
実際の請求項・解決手段に基づいた評価を行う。

出力 JSON のみ (markdown コードブロックも不要):
{
  "verdict": "GO/MAYBE/NO-GO",
  "real_bom_jpy": 整数 (実本文ベースの BOM 合計),
  "bom_breakdown": [
    {"part": "...", "estimated_cost": 整数, "source_hint": "..."}
  ],
  "manufacturing_complexity": "low/medium/high",
  "certification_required": [文字列リスト],
  "moq_realistic": "1個/100個/500個/1000個" (受注生産可能性),
  "competitor_analysis": {
    "median_price_jpy": 整数,
    "saturation": "low/medium/high",
    "differentiation_axes": [文字列リスト, 既存品にないもの]
  },
  "price_advantage_score": 1-10 (10=圧倒的優位、1=価格で勝負できない),
  "differentiation_score": 1-10,
  "execution_risk_score": 1-10 (10=低リスク),
  "recommended_retail_jpy": 整数 (現実的に売れる価格),
  "estimated_margin_pct": 小数1位 (上記価格で OEM 100個発注時),
  "summary": "100字以内で結論",
  "main_concerns": ["...", "..."] (3-5個),
  "next_actions": ["...", "..."] (3-5個)
}
"""


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    idx = text.find('"verdict"')
    if idx == -1:
        return None
    open_idx = text.rfind("{", 0, idx)
    if open_idx == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(open_idx, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[open_idx : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def evaluate_pdca(patent: dict, patent_text: dict, competitor_data: dict, model: str = "haiku") -> dict:
    """全データを Claude に投げて判定"""
    if not shutil.which("claude"):
        return {"_error": "claude CLI not available"}

    # 入力サイズを抑える
    text_summary = {
        "title": patent_text.get("title", patent.get("title", "")),
        "abstract": patent_text.get("abstract", "")[:2000],
        "claims": patent_text.get("claims", "")[:1500],
        "applicant": patent_text.get("applicant", patent.get("assignee", "")),
        "inventor": patent_text.get("inventor", ""),
    }

    comp_summary = {
        "competitors_top5": [
            {"title": c["title"][:80], "price_jpy": c.get("price_jpy")}
            for c in competitor_data.get("competitors", [])[:5]
        ],
        "price_distribution": competitor_data.get("price_distribution", {}),
        "saturation_level": competitor_data.get("saturation_level", ""),
        "sponsored_ratio": competitor_data.get("sponsored_ratio", 0),
    }

    user_prompt = f"""【特許情報】
{json.dumps(text_summary, ensure_ascii=False, indent=2)}

【Claude 初期評価 (タイトルベース、参考)】
カテゴリ: {patent.get('category', '')}
推定原価 (推測): ¥{patent.get('estimated_unit_cost_jpy', 0):,}
推定小売 (推測): ¥{patent.get('estimated_retail_jpy', 0):,}
推定粗利 (推測): {patent.get('estimated_margin_pct', 0)}%

【Amazon JP 実競合データ】
{json.dumps(comp_summary, ensure_ascii=False, indent=2)}

【判定依頼】
特許本文と競合実データから、事業として GO/MAYBE/NO-GO を判定してください。
重要: 初期評価の数字は参考。本文ベースで再見積もりしてください。
JSON のみ出力。
"""

    cmd = [
        "claude",
        "-p", user_prompt,
        "--model", model,
        "--output-format", "json",
        "--append-system-prompt", PDCA_SYSTEM,
        "--no-session-persistence",
        "--disable-slash-commands",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return {"_error": "claude timeout 180s"}

    if r.returncode != 0:
        return {"_error": f"claude exit {r.returncode}"}

    try:
        outer = json.loads(r.stdout)
        result_text = outer.get("result", "")
    except json.JSONDecodeError:
        return {"_error": "outer json"}

    parsed = _extract_json(result_text)
    if not parsed:
        return {"_error": "inner parse failed", "_raw": result_text[:500]}

    return parsed


def generate_search_query(patent: dict, patent_text: dict) -> str:
    """特許情報から Amazon JP 検索用クエリを生成"""
    title = patent_text.get("title") or patent.get("title", "")
    # 簡易版: タイトルから主要 2-3 語を抽出
    # 「【】」「ペット用」「自動」などのノイズ削除
    cleaned = re.sub(r"[【】\(\)（）]", " ", title)
    cleaned = re.sub(r"(及び|機能付|装置|の構造|機構|方法|システム)", " ", cleaned)
    words = [w for w in re.split(r"\s+", cleaned) if len(w) >= 2]
    if len(words) >= 3:
        return " ".join(words[:3])
    return title[:30]


def run_pdca_for_patent(patent: dict, headless: bool = True) -> dict:
    """1 候補に対する完全 PDCA フロー"""
    patent_number = patent.get("patent_number", "")
    logger.info(f"=== PDCA: {patent_number}: {patent.get('title', '')[:50]} ===")

    # Step 1: 特許本文取得
    logger.info(f"  [1/3] J-PlatPat 本文取得...")
    patent_text = fetch_patent_text(patent_number, headless=headless)
    if "_error" in patent_text:
        logger.warning(f"    ✗ 本文取得失敗: {patent_text['_error']}")
        return {"patent_number": patent_number, "_error": "patent_text_fetch_failed", **patent_text}

    # Step 2: Amazon JP 競合検索
    query = generate_search_query(patent, patent_text)
    logger.info(f"  [2/3] Amazon JP 検索: '{query}'")
    competitor_data = search_amazon_jp(query, max_results=12, headless=headless)
    if "_error" in competitor_data:
        logger.warning(f"    ✗ 競合検索失敗: {competitor_data['_error']}")
        # 失敗してもPDCA は続行 (空データで)
        competitor_data = {"competitors": [], "price_distribution": {}, "saturation_level": "unknown"}

    # Step 3: Claude PDCA 判定
    logger.info(f"  [3/3] Claude PDCA 評価...")
    verdict = evaluate_pdca(patent, patent_text, competitor_data)
    if "_error" in verdict:
        logger.warning(f"    ✗ PDCA 評価失敗: {verdict['_error']}")
        return {"patent_number": patent_number, "_error": "pdca_eval_failed", **verdict}

    # 統合
    full_result = {
        "patent_number": patent_number,
        "title": patent_text.get("title", patent.get("title", "")),
        "claude_initial_score": patent.get("total"),
        "claude_initial_quality": patent.get("_quality_score"),
        "patent_text": patent_text,
        "competitor_data": competitor_data,
        "pdca_verdict": verdict,
        "_timestamp": datetime.now().isoformat(),
    }

    # 結果保存
    safe_num = patent_number.replace("/", "_").replace(" ", "_")
    out_path = PDCA_DIR / f"pdca_{safe_num}.json"
    out_path.write_text(json.dumps(full_result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"  ✓ 保存: {out_path.name}")

    # サマリー出力
    v = verdict
    logger.info(f"    判定: {v.get('verdict', '?')} (BOM ¥{v.get('real_bom_jpy', 0):,} → 推奨小売 ¥{v.get('recommended_retail_jpy', 0):,}, 粗利 {v.get('estimated_margin_pct', 0)}%)")
    logger.info(f"    価格優位: {v.get('price_advantage_score', 0)}/10, 差別化: {v.get('differentiation_score', 0)}/10, 飽和: {competitor_data.get('saturation_level', '?')}")

    return full_result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--patent-number", type=str, help="単一特許の PDCA")
    parser.add_argument("--top-n", type=int, default=3, help="all_viable.json から Top N に PDCA")
    parser.add_argument("--skip-existing", action="store_true", help="既に PDCA 結果がある特許はスキップ")
    args = parser.parse_args()

    if args.patent_number:
        # 単一特許
        viable_path = RESULTS_DIR / "all_viable.json"
        viable = json.load(open(viable_path, encoding="utf-8")) if viable_path.exists() else []
        target = next((p for p in viable if p.get("patent_number") == args.patent_number), None)
        if not target:
            target = {"patent_number": args.patent_number, "title": ""}
        run_pdca_for_patent(target)
    else:
        # Top N
        viable_path = RESULTS_DIR / "all_viable.json"
        if not viable_path.exists():
            logger.error("all_viable.json なし、aggregate_candidates.py を先に実行")
            return 1
        viable = json.load(open(viable_path, encoding="utf-8"))
        top_n = viable[: args.top_n]
        logger.info(f"=== Top {len(top_n)} 候補に PDCA 実行 ===")

        for patent in top_n:
            num = patent.get("patent_number")
            existing = PDCA_DIR / f"pdca_{num.replace('/', '_').replace(' ', '_')}.json"
            if args.skip_existing and existing.exists():
                logger.info(f"  スキップ (既存): {num}")
                continue
            try:
                run_pdca_for_patent(patent)
            except Exception as e:
                logger.warning(f"  例外: {num}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
