"""カテゴリ別検索キーワード集

note_ai_mousigo 記事の推奨カテゴリ:
- 日用品 (家庭用品)
- キッチンツール
- 文房具
- ペット用品
- 介護用品
- DIY 工具
- 収納グッズ
- 育児用品

これらに「売れる」「シンプルに作れる」観点を加味して、
具体的なキーワードを並べる（粒度を細かくし結果を絞る）。

運用方針: 1 日 1-3 キーワード × 15-20 件取得。
週で 100-150 件、月で 500-800 件の規模を目標。
"""

from __future__ import annotations

# カテゴリ別キーワードリスト
CATEGORY_KEYWORDS = {
    "kitchen": [
        "キッチン 便利 構造",
        "調理 補助 器具",
        "計量カップ 一体",
        "包丁立て 構造",
        "鍋蓋 立てる",
        "保存容器 密閉",
        "まな板 折り畳み",
        "皮むき 構造",
    ],
    "pet": [
        "ペット 自動給水 サイフォン",
        "猫 トイレ 構造",
        "犬 ハーネス 構造",
        "ペット 玩具 噛む",
        "ペット 食器 滑り止め",
        "ペット 抜け毛 ブラシ",
        "鳥カゴ 給餌 構造",
    ],
    "elderly_care": [
        "介護 立ち上がり 補助",
        "歩行 補助 折り畳み",
        "入浴 介護 椅子",
        "食事 補助 スプーン",
        "握力 補助 構造",
        "高齢者 トイレ 補助",
    ],
    "stationary": [
        "ペン 持ち手 構造",
        "クリップ 構造",
        "消しゴム ホルダー",
        "定規 折り畳み",
        "メモ 整理 構造",
        "ホッチキス 補助",
    ],
    "diy_tools": [
        "片手 クランプ ラチェット",
        "ノコギリ ガイド",
        "ドリル 補助 構造",
        "計測 構造 工具",
        "DIY 接続 構造",
    ],
    "storage": [
        "収納 折り畳み 構造",
        "省スペース ハンガー",
        "押入れ 仕切り 構造",
        "引き出し 整理 構造",
        "靴 収納 構造",
    ],
    "baby": [
        "育児 抱っこ 補助",
        "おむつ 構造",
        "離乳食 計量",
        "ベビーカー 構造",
        "授乳 補助 クッション",
    ],
    "household": [
        "洗濯 折り畳み 物干し",
        "掃除 構造 ブラシ",
        "ハンガー 滑り止め 構造",
        "タオル 掛け 構造",
        "ドアストッパー 構造",
        "傘立て 構造",
    ],
}


def get_keyword_for_today(date_str: str = None) -> tuple[str, str]:
    """日付から決定論的にキーワードを 1 つ選択

    毎日違うカテゴリ × キーワードを取得することで偏りを防ぐ。
    """
    from datetime import datetime
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 全キーワードをリスト化
    all_kws: list[tuple[str, str]] = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            all_kws.append((cat, kw))

    # date_str をハッシュ化してインデックス取得
    import hashlib
    h = int(hashlib.md5(date_str.encode()).hexdigest(), 16)
    idx = h % len(all_kws)
    return all_kws[idx]


def list_all_keywords() -> list[tuple[str, str]]:
    """全カテゴリ × キーワード"""
    out: list[tuple[str, str]] = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            out.append((cat, kw))
    return out


if __name__ == "__main__":
    print(f"Total categories: {len(CATEGORY_KEYWORDS)}")
    total = sum(len(kws) for kws in CATEGORY_KEYWORDS.values())
    print(f"Total keywords: {total}")
    cat, kw = get_keyword_for_today()
    print(f"Today: {cat} - {kw}")
