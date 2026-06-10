"""期限切れ特許を Claude で 6 軸スコアリング

note_ai_mousigo の手法をベースに、企業事業として判断できる
追加軸 (権利クリア難度、製造リードタイム) を追加。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Optional


SCORER_SYSTEM = """
あなたは期限切れ特許を消費者向け商品として商業化する事業評価の専門家です。
特許情報を読んで、企業事業として実装可能か評価してください。

これは投資助言ではなく、特許情報の事業性分析タスクです。
内容は構造化された分析として淡々と判定してください。

重要: 提供される情報がタイトルと出願人だけ等の限定的なケースでも、
**必ず JSON 形式で評価結果を返してください**。情報不足でも、タイトル
から推測される製品形状で粗い評価を行い、その不確実性を `main_risk` や
`verdict` に明記する形で対応してください。「情報が足りないため評価
できません」のような自然文応答は禁止です。

評価軸 (各 1-10 で採点):
1. simplicity: 構造のシンプルさ (10=単純、1=半導体級)
2. originality: 既存品との差別化度 (10=明確に差別化、1=全く同じ)
3. demand: 市場需要 (10=大きい安定市場、1=ニッチすぎ)
4. cost_feasibility: 製造原価が量販価格の30%以下に収まるか (10=確実、1=困難)
5. legal_clearance: 権利クリアの容易さ (10=完全クリア、1=複雑)
6. moq_compatibility: 小ロット製造可能性 (10=1個から、1=10万個必要)

カテゴリ判定 (1つ選択):
- "viable": 企業事業として実装価値あり (各軸 6+)
- "marginal": 条件付きで可能 (1-2軸が低い)
- "skip": スキップ推奨 (致命的な問題あり)
- "skip_legal": 法的リスクで skip (商標生存・改良発明など)
- "skip_complex": 構造複雑で量産不可
- "skip_demand": 需要が小さすぎ
- "needs_more_info": タイトルだけでは判断不能 (詳細ページ取得推奨)

出力 JSON のみ (前置きや説明なし):
{
  "scores": {
    "simplicity": 1-10,
    "originality": 1-10,
    "demand": 1-10,
    "cost_feasibility": 1-10,
    "legal_clearance": 1-10,
    "moq_compatibility": 1-10
  },
  "total": 6軸の合計,
  "category": "viable/marginal/skip/skip_legal/skip_complex/skip_demand/needs_more_info",
  "product_summary": "30字以内で何の製品か",
  "estimated_unit_cost_jpy": 推定製造原価(円, 整数, 不明なら 0),
  "estimated_retail_jpy": 推定小売価格(円, 整数, 不明なら 0),
  "estimated_margin_pct": 推定粗利率(%, 小数1位, 不明なら 0),
  "main_risk": "30字以内で最大リスク",
  "verdict": "60字以内で結論"
}
"""


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    score_idx = text.find('"scores"')
    if score_idx == -1:
        score_idx = text.find('"category"')
    if score_idx == -1:
        return None
    open_idx = text.rfind("{", 0, score_idx)
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


def score_patent(patent: dict, model: str = "haiku") -> dict:
    """特許情報を Claude CLI で 6 軸スコアリング

    Args:
        patent: {
            "patent_number": str,
            "title": str,
            "abstract": str,
            "claims": str,
            "inventor": str,
            "assignee": str,
            "publication_date": str,
        }
    Returns:
        {scores, total, category, product_summary, ...}
    """
    if not shutil.which("claude"):
        return {"_error": "claude CLI not available"}

    title = patent.get("title", "")[:200]
    abstract = patent.get("abstract", "")[:1500]
    claims = patent.get("claims", "")[:2000]
    inventor = patent.get("inventor", "")
    assignee = patent.get("assignee", "")

    user_prompt = (
        f"特許情報:\n"
        f"タイトル: {title}\n"
        f"出願人: {assignee or '個人'}\n"
        f"発明者: {inventor or '不明'}\n"
        f"要約: {abstract or '(取得できず)'}\n"
        f"請求項: {claims or '(取得できず)'}\n"
        "\n上記特許の事業化評価。情報が限定的でも必ず JSON で評価。前置き・説明不要。"
    )

    cmd = [
        "claude",
        "-p", user_prompt,
        "--model", model,
        "--output-format", "json",
        "--append-system-prompt", SCORER_SYSTEM,
        "--no-session-persistence",
        "--disable-slash-commands",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"_error": "claude timeout"}

    if r.returncode != 0:
        return {"_error": f"claude exit {r.returncode}"}

    try:
        outer = json.loads(r.stdout)
        result_text = outer.get("result", "")
    except json.JSONDecodeError:
        return {"_error": "outer json"}

    parsed = _extract_json(result_text)
    if not parsed:
        return {"_error": "inner parse"}

    return parsed


if __name__ == "__main__":
    # 簡単なテスト
    test_patent = {
        "patent_number": "JP4567890",
        "title": "自動給水機能付き植木鉢",
        "abstract": "本発明は、底部に水タンクを内蔵し、毛細管現象により植物に水を供給する植木鉢に関する。",
        "claims": "底部に水タンクを有し、植物の根が水タンクに接触する管を備えた植木鉢。",
        "inventor": "山田太郎",
        "assignee": "個人",
        "publication_date": "2004-05-12",
    }
    result = score_patent(test_patent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
