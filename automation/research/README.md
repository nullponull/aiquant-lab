# 日次リサーチコレクター

連載「AIで投資の壁を越える」と Brain B戦略 SKU の**素材を毎日自動収集**する仕組み。

---

## 目的

連載・SKU の執筆では「実例」「失敗事例」「時事ネタ」が常に必要。
ちょる子記事のような材料が偶然見つかるのを待つのではなく、**毎日自動で
収集 → LLM 分類 → 用途別フォルダに保存**する。

---

## アーキテクチャ

```
[毎日 23:00]
        ↓
collector.py が起動
        ↓
複数ソースから記事/ツイートを取得
  ├─ Yahoo Finance JP (RSS)
  ├─ note タグフィード (#投資 #AI #NISA)
  ├─ ダイヤモンド・オンライン (RSS)
  ├─ 東洋経済オンライン (RSS)
  └─ X 検索 (xpost-community のクッキー流用)
        ↓
Claude CLI で各記事をスコアリング & 分類
  ├─ interestingness: 1-10
  ├─ category: SKU5候補 / 連載素材 / 業界動向
  └─ relevant_sku_or_episode: SKU 5, 連載第6回, etc.
        ↓
スコア 6 以上だけ保存
        ↓
data/research_inbox/YYYY-MM-DD/
  ├─ raw_items.json     (全取得アイテム)
  ├─ filtered.json       (スコア6+のアイテム)
  └─ digest.md           (上位10件の要約)
        ↓
高評価 (8+) アイテムは
brain-post-system/aiquant_products/assets/research_sources/
にも自動コピー
```

---

## ファイル構成

```
automation/research/
├── README.md                # 本ファイル
├── collector.py             # メインスクリプト
├── sources/
│   ├── __init__.py
│   ├── base.py             # 共通インターフェース
│   ├── rss.py              # RSS フェッチャー (Yahoo / Diamond / Toyo)
│   ├── note.py             # note タグフィード
│   └── x_search.py         # X キーワード検索 (xpost-community)
├── classifier.py            # Claude CLI でスコアリング & 分類
├── digest.py                # 日次 digest 生成
├── run.sh                   # systemd 用ラッパー
├── research-collector.service
└── research-collector.timer
```

---

## カテゴリ分類

各アイテムを以下のいずれかに分類:

| カテゴリ | 内容 | 行き先 |
|---------|------|------|
| `sku5_scam` | AI 投資詐欺っぽい煽り投稿 / 商材 | SKU 5 (詐欺解剖) DB 候補 |
| `sku5_credible` | 信頼できる投資論 (ちょる子型) | SKU 5 対極事例 |
| `series_material` | 連載エピソードの素材 | 該当回の補強 |
| `regime_change` | 市場構造変化 (東証改革、政策等) | 連載第2壁 (非定常性) 素材 |
| `failure_case` | 戦略の失敗事例 | 連載 + SKU 共通 |
| `tool_release` | 新しい AI / 投資ツール | 業界動向 |
| `competitor` | 類似商材ローンチ | Brain 戦略再考材料 |
| `discard` | 関係なし | 破棄 |

---

## スコアリング基準

Claude CLI に以下を投げて判定:

```
記事タイトル: {title}
記事本文: {body[:500]}

以下の基準で 1-10 でスコアしてください:
1-3: 関係ない / 一般的すぎ
4-6: 軽く参考になる程度
7-8: 具体的事例として使える
9-10: そのまま記事や商材に引用できるレベル

連載「AIで投資の壁を越える」(AI×投資の限界を実装で確かめる) と
Brain SKU 5「AI投資詐欺の数学的解剖」の文脈で評価してください。

出力: スコア + カテゴリ (sku5_scam / sku5_credible / series_material /
regime_change / failure_case / tool_release / competitor / discard)
```

---

## ソース別の詳細

### Yahoo Finance JP
- RSS: https://news.yahoo.co.jp/rss/categories/business.xml
- 取得頻度: 1 日 1 回 (50 件)
- 抽出条件: 「投資」「AI」「NISA」を含むタイトル

### note タグフィード
- URL パターン: https://note.com/api/v3/hashtags/{tag}/notes
- 対象タグ: 投資, AI, NISA, つみたて, 株, クオンツ, 副業 AI
- 取得頻度: 1 日 1 回 (タグごとに 20 件)

### ダイヤモンド・オンライン
- RSS: https://diamond.jp/feed/news/economics_money
- 取得頻度: 1 日 1 回

### 東洋経済オンライン
- RSS: https://toyokeizai.net/list/feed/rss
- 取得頻度: 1 日 1 回

### X 検索
- xpost-community/.x_cookies.json を流用
- キーワード: 「AI 投資」「ChatGPT 株」「自動売買」「年利」「月利」等
- 取得頻度: 1 日 1 回 (キーワードごとに 20 件)

---

## 出力例

### data/research_inbox/2026-04-29/digest.md

```markdown
# 2026-04-29 リサーチダイジェスト

総取得: 187 件 | フィルタ後: 23 件 | 上位: 10 件

## トップ 10

### 1. [9.0/10 sku5_credible] 「240万円⇒4億円超」にした投資家・ちょる子さん...
- 出典: ダイヤモンド・ザイ
- 公開: 2026-04-29 21:20
- URL: https://...
- 用途: SKU 5 第8章 補論「信頼できる投資論の特徴」
- メモ: 東証改革効果、TOPIX一択、AGC ウクライナ再建ストーリー

### 2. [8.5/10 sku5_scam] 「AIで月利10%確実」系ツイート (匿名化)
...
```

---

## 運用

### 起動
```bash
systemctl --user start research-collector.timer
systemctl --user enable research-collector.timer
```

### ログ確認
```bash
journalctl --user -u research-collector -n 100
```

### 手動実行
```bash
cd /home/sol/aiquant-lab
uv run python automation/research/collector.py --dry-run
uv run python automation/research/collector.py
```

---

## 容量管理

- 90 日経過した raw_items.json は自動圧縮
- 1 年経過したものは自動削除
- 高評価 (スコア 8+) のみ research_sources/ に永続保存

---

## コスト見積もり

- LLM 分類: 1 日 200 件 × 入力 500 トークン = 100K トークン
- Claude Haiku 4.5: 100K × $1/1M = $0.10
- 月: $3-5 程度

これは Brain 商材売上から十分回収可能。
