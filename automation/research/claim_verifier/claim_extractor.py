"""LLM で主張を構造化抽出

入力: research_inbox の filtered.json アイテム
出力: 検証可能な claim の構造化 dict 群

「明日 BTC が 50% 上がる」「来週 NVDA は買い」のような検証可能な
主張だけを抽出する。具体性の低い主張 (「いつか上がる」等) は無視。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Optional

EXTRACTOR_SYSTEM = """
あなたは投資・金融コンテンツの主張抽出器です。
記事や SNS 投稿から、**検証可能な予測/主張**だけを構造化抽出します。

抽出対象 (CLAIMABLE):
- 銘柄/資産が明示されている (BTC, ETH, SPY, AAPL, 7203 など)
- 方向が明示できる (上がる/下がる/横ばい)
- 期間が推定できる (時間/日/週/月)
- 具体的なリターン目標があると尚良し

抽出対象外 (SKIP):
- 「いつか必ず上がる」のように期間がない
- 抽象的な戦略論、市場全体論
- 「今日のニュース要約」など主張なし
- 過去形の自慢話 (「昨日 50% 取れた」など、未来の主張がない)
- 単なる商品レビュー、レポート

複数主張が含まれる場合は、最も明確な主張 1 つだけ抽出。

出力 JSON schema:
{
  "is_claimable": true/false,
  "claims": [   // 0 or 1 element
    {
      "asset": "BTC",                    // ティッカー or 銘柄コード
      "asset_class": "crypto",           // crypto/us_stock/jp_stock/fx
      "direction": "LONG",               // LONG/SHORT/NEUTRAL
      "horizon_hours": 72,               // 数値時間
      "target_pct": 50,                  // 期待リターン% or null
      "target_price": null,              // 価格目標 or null
      "conviction_score": 7,             // 1-10 主張の確信度
      "reasoning_hint": "30字以内"
    }
  ]
}

重要: JSON のみ出力。前置きや説明不要。
"""


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    score_idx = text.find("is_claimable")
    if score_idx == -1:
        score_idx = text.find("claims")
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


def extract_claim(item: dict, model: str = "haiku") -> dict:
    """1 アイテムから主張を抽出

    Returns: {"is_claimable": bool, "claims": [...]}
    """
    if not shutil.which("claude"):
        return {"is_claimable": False, "claims": [], "_error": "no claude CLI"}

    title = (item.get("title") or "")[:200]
    body = (item.get("body") or "")[:1000]
    source = item.get("source", "")

    user_prompt = (
        f"記事タイトル: {title}\n"
        f"本文: {body}\n"
        f"出典: {source}\n"
        "\n上記から検証可能な主張を抽出してください。JSON のみ出力。"
    )

    cmd = [
        "claude",
        "-p", user_prompt,
        "--model", model,
        "--output-format", "json",
        "--append-system-prompt", EXTRACTOR_SYSTEM,
        "--no-session-persistence",
        "--disable-slash-commands",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return {"is_claimable": False, "claims": [], "_error": "timeout"}

    if r.returncode != 0:
        return {"is_claimable": False, "claims": [], "_error": f"exit {r.returncode}"}

    try:
        outer = json.loads(r.stdout)
        result_text = outer.get("result", "")
    except json.JSONDecodeError:
        return {"is_claimable": False, "claims": [], "_error": "outer json"}

    parsed = _extract_json(result_text)
    if not parsed:
        return {"is_claimable": False, "claims": [], "_error": "inner parse"}

    # 検証
    is_claimable = bool(parsed.get("is_claimable"))
    claims = parsed.get("claims", []) or []

    valid_claims = []
    for c in claims[:1]:  # 念のため最大 1 件
        if not isinstance(c, dict):
            continue
        try:
            asset = (c.get("asset") or "").upper()
            if not asset:
                continue
            direction = (c.get("direction") or "").upper()
            if direction not in ("LONG", "SHORT", "NEUTRAL"):
                continue
            horizon = float(c.get("horizon_hours") or 0)
            if horizon < 1 or horizon > 720:  # 1時間〜30日
                continue
            valid_claims.append({
                "asset": asset,
                "asset_class": (c.get("asset_class") or "us_stock").lower(),
                "direction": direction,
                "horizon_hours": horizon,
                "target_pct": float(c["target_pct"]) if c.get("target_pct") not in (None, "") else None,
                "target_price": float(c["target_price"]) if c.get("target_price") not in (None, "") else None,
                "conviction_score": int(c.get("conviction_score") or 5),
                "reasoning_hint": (c.get("reasoning_hint") or "")[:60],
            })
        except (TypeError, ValueError):
            continue

    return {"is_claimable": is_claimable and bool(valid_claims), "claims": valid_claims}


def claim_to_db_record(item: dict, claim: dict) -> dict:
    """抽出結果を DB スキーマに合わせた dict に変換"""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=claim["horizon_hours"])
    return {
        "detected_at": now.isoformat(),
        "source_item_url": item.get("url", ""),
        "source_name": item.get("source", ""),
        "source_author": item.get("author"),
        "raw_text": (item.get("title", "") + " | " + (item.get("body", "")))[:1500],
        "asset": claim["asset"],
        "asset_class": claim["asset_class"],
        "direction": claim["direction"],
        "horizon_hours": claim["horizon_hours"],
        "target_pct": claim.get("target_pct"),
        "target_price": claim.get("target_price"),
        "conviction_score": claim.get("conviction_score"),
        "expires_at": expires.isoformat(),
        "extracted_meta": {
            "reasoning_hint": claim.get("reasoning_hint", ""),
        },
    }


if __name__ == "__main__":
    test = {
        "title": "ClaudeにKronosを使って次のBTCローソク足を予測するよう指示しました。1晩で+$4,200。",
        "body": "Kronosは45の取引所から12億個のローソク足で訓練されたGPTスタイルのモデル。72時間で$300→$4,500。",
        "source": "x_search",
        "author": "@RetroChainer",
        "url": "https://x.com/RetroChainer/status/2049565701971820854",
    }
    r = extract_claim(test)
    print(json.dumps(r, ensure_ascii=False, indent=2))
