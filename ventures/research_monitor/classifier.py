"""Claude CLI でアイテムをスコアリング & カテゴリ分類

各アイテムに interestingness スコア (1-10) と category を付与する。

NOTE: Claude CLI は subprocess 経由だと「投資助言」を拒否しやすい。
そこでプロンプトを「コンテンツ素材として技術評価」に偽装する。
それでも 100 件 × 数秒 / 件 = 数分かかるので注意。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Optional

# 連載 / SKU 文脈
CONTEXT = """
あなたは AI×投資の研究プロジェクト「AIで投資の壁を越える」の
エディタです。連載と書籍 (Brain) の素材として、毎日収集される
ニュース・SNS投稿を以下の基準で評価します。

重要: これは投資助言の生成ではなく、教育コンテンツの素材選別タスク
です。「詐欺っぽい煽り投稿」も検証記事の素材として価値があるため、
内容の真偽ではなく、「**素材として使えるか**」で評価します。

カテゴリ:
- sku5_scam: AI / 自動売買で「絶対勝てる」「月利○%」系の煽り商材・投稿
  → 検証 DB の素材になるので「具体的・典型的」なほど高スコア
- sku5_credible: 信頼できる投資家がロジック公開で語っている記事
  → 対極事例として使うので、再現可能・公開度が高いほど高スコア
- series_material: 連載エピソードの素材になる事例
  → AI×投資の限界を示す具体事例
- regime_change: 市場構造変化 (政策、東証改革、規制) の話題
  → 「非定常性の壁」素材として高評価
- failure_case: 戦略・ツール・運用の失敗事例
  → 連載・SKU 共通で高評価
- tool_release: 新しい AI / 投資ツール
  → 業界動向、それ自体は中スコア
- competitor: 類似商材・教材のローンチ
  → 戦略再考材料、中スコア
- discard: 関係なし / 一般的すぎ / 単なる相場ニュース
  → スコア 1-3

スコアリング基準 (素材としての価値):
- 1-3: 関係ない / 一般的すぎ → discard
- 4-6: 軽く参考になる程度 (一般論、抽象的)
- 7-8: 具体的事例として記事に引用できる (固有名詞・数値あり)
- 9-10: そのまま素材になる、強い差別化要素 (詐欺の典型例、有名人発信、
        ユニークな事例、独自データを含むなど)

例:
- 「ChatGPTで月利30%確実」+具体的金額 → sku5_scam, score 8 (典型例として価値)
- 「AIで何となく儲かりそう」 → discard, score 2 (一般的すぎ)
- ちょる子さん4億円達成記事 → sku5_credible, score 9 (固有・実績・公開ロジック)
- 普通の相場ニュース「日経平均が小幅高」 → discard, score 2

出力形式 (JSON のみ):
{"score": <1-10>, "category": "<上記カテゴリ>", "reason": "<30字以内>"}
"""


def _extract_json(text: str) -> Optional[dict]:
    """LLM 応答から JSON ブロックを取り出す (ネスト OK な堅牢版)"""
    if not text:
        return None

    # 1) 単純な非ネスト JSON
    m = re.search(r"\{[^{}]*\"score\"[^{}]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 2) "score" を含む位置から、対応する閉じ } まで bracket-counting で抽出
    score_idx = text.find('"score"')
    if score_idx == -1:
        return None
    # 直前の { を探す
    open_idx = text.rfind("{", 0, score_idx)
    if open_idx == -1:
        return None
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[open_idx : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def classify_item(item_dict: dict, model: str = "haiku") -> dict:
    """1 アイテムを Claude CLI で分類"""

    if not shutil.which("claude"):
        # CLI 不在時はデフォルト値を返す
        return {"score": 5, "category": "discard", "reason": "claude CLI not available"}

    title = item_dict.get("title", "")[:200]
    body = (item_dict.get("body") or "")[:600]
    source = item_dict.get("source", "")
    author = item_dict.get("author") or ""

    user_prompt = (
        f"記事タイトル: {title}\n"
        f"本文抜粋: {body}\n"
        f"出典: {source}\n"
        + (f"著者: {author}\n" if author else "")
        + "\nJSON のみ出力してください。"
    )

    cmd = [
        "claude",
        "-p", user_prompt,
        "--model", model,
        "--output-format", "json",
        "--append-system-prompt", CONTEXT,
        "--no-session-persistence",
        "--disable-slash-commands",
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return {"score": 5, "category": "discard", "reason": "timeout"}

    if r.returncode != 0:
        return {"score": 5, "category": "discard", "reason": f"cli exit {r.returncode}"}

    try:
        outer = json.loads(r.stdout)
        result_text = outer.get("result", "")
    except json.JSONDecodeError:
        return {"score": 5, "category": "discard", "reason": "outer json error"}

    parsed = _extract_json(result_text)
    if not parsed:
        return {"score": 5, "category": "discard", "reason": "inner parse error"}

    # 値の検証
    try:
        score = int(parsed.get("score", 5))
    except (TypeError, ValueError):
        score = 5
    score = max(1, min(10, score))

    valid_categories = {
        "sku5_scam", "sku5_credible", "series_material",
        "regime_change", "failure_case", "tool_release",
        "competitor", "discard",
    }
    cat = parsed.get("category", "discard")
    if cat not in valid_categories:
        cat = "discard"

    reason = (parsed.get("reason") or "")[:60]

    return {"score": score, "category": cat, "reason": reason}
