# X 連投スレッド投稿手順 — 番外編「第7の壁」記事告知

> 作成日: 2026-05-17
> 対象記事: [note #005 番外編](https://note.com/ai_compass_media/n/n73cb83517fd3)
> 投稿元アカウント: [@ぬるぽん (@nullpodesu)](https://x.com/nullpodesu)
> 配信プラン: 火 20:00 予告 → 水 12:00 メイン5連投 → 水 18:00 補足 → 木朝・金昼

---

## 投稿の選択肢

### A. 手動投稿（推奨・初回）

X 公式アプリ/Web から、[`promo/005_episode_bangai_x.md`](../promo/005_episode_bangai_x.md) のテンプレを順にコピペで投稿。

**スレッド連投の手順**:
1. Tweet 1（フック）を **画像添付** (`005_wall7_x.png`, 1200×675) で投稿
2. 投稿後、自分のツイートに **「リプライ」** で Tweet 2 を投稿
3. 同様に Tweet 3, 4, 5 をリプライチェーンで連投
4. 全体で5連投スレッドが完成

**画像添付場所**: `/home/sol/aiquant-lab/promo/005_wall7_x.png`

### B. xpost-community 自動投稿スクリプト経由

```bash
cd /home/sol/xpost-community
python3 scripts/original_post.py \
  --text "$(head -1 /home/sol/aiquant-lab/promo/005_episode_bangai_x.md)" \
  --thread-file /home/sol/aiquant-lab/promo/005_episode_bangai_x.md \
  --image /home/sol/aiquant-lab/promo/005_wall7_x.png
```

※ xpost-community が thread モードに対応している場合のみ。
未対応なら手動投稿を推奨。

### C. note公開時のシェア機能を使う

note管理画面の「公開後にXに自動投稿」機能を使う。ただしテンプレ通りにならないため、簡易告知用。

---

## 投稿タイムライン詳細

### Day 1（火）20:00 — 予告ツイート（単発）

ターゲット時間: 平日夜の通勤後ピーク（19-21時）
内容: [`005_episode_bangai_x.md`](../promo/005_episode_bangai_x.md) の「火 20:00 — 予告」セクション

### Day 2（水）12:00 — メインスレッド（5連投）

ターゲット時間: 平日昼休み開始（12:00-12:30）
内容: Tweet 1 → 5 を連投

注意: **noteの公開を 11:45 までに完了** してから 12:00 にTweet 1 を投稿。
（Tweet 1 の note URL は `https://note.com/ai_compass_media/n/n73cb83517fd3` で確定済）

### Day 2（水）18:00 — 補足リプライ

ターゲット時間: 退社後（18:00-19:00）
内容: 5連投スレッドの末尾にさらにリプライで「免責補足」ツイート

### Day 3（木）朝 — 反響共有

ターゲット時間: 通勤時間（7-9時）
内容: 「地味に反響をもらっている」と引用RT or 単発で

### Day 4（金）昼 — データ深掘り

ターゲット時間: 昼休み（12-13時）
内容: 反実仮想シミュレーション結果を1ツイートで紹介

---

## 投稿後の運用

### 24時間後チェック

- インプレッション数（目標: 5,000以上）
- いいね率（目標: 1%以上 = 50いいね以上）
- リプライ数（目標: 3以上）
- note記事クリック数（Google Analytics 確認）

### 1週間後分析

- noteの購入数 → 目標100部 (¥30万売上)
- メンバーシップ Premium 新規入会数
- X フォロワー増加数

---

## NG表現チェック（投稿前に再確認）

[`xpost-community/config/brand_voice_codex.json`](../../xpost-community/config/brand_voice_codex.json) 準拠:

- ❌ 「絶対」「100%」「必ず」 → 投資文脈で景品表示法違反リスク
- ❌ 感嘆符 → 使わない
- ❌ 過剰なemoji → 最大1個 (🧵 のみ使用済)
- ❌ 「私が」「僕が」 → 主アカは「ぬるぽん」なのでOK（一人称使ってよい）

---

## 拡散の追加施策

### 検証屋アカウント（review_account）から朝6時にレビュー投稿

`/home/sol/daily-note-post/` の自動投稿で:
```bash
cd /home/sol/daily-note-post
NOTE_POST_STATE_PATH=/home/sol/.note-state-review.json \
python3 generate_review_article.py --target n73cb83517fd3
```

### note 内サーキュレーション
他のAIコンパス記事の末尾に「関連記事」として今回の番外編リンクを追加
→ ai-blog-system の `_includes/related-posts.html` を編集（必要なら）

---

## 緊急ロールバック

投稿後にコンプライアンス問題等が発覚した場合:
1. X からツイート削除（スレッド全体）
2. note記事を **下書きに戻す**
3. info@ai-media.co.jp で関係者通知

note管理画面: https://note.com/ai_compass_media/notes
