# AIで投資の壁を越える

> AI が「市場予測は無理」と言われ続けている領域に、実装でどこまで迫れるかを検証する公開研究プロジェクト

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-active-green.svg)]()

---

## 何をしているプロジェクトか

AI でコーディング、文章生成、画像認識、設計、解析 ── できることのリストは日々増えています。ただ「市場予測」だけは、不思議なくらい昔から「無理」と言われ続けています。Renaissance や Two Sigma のような最先端の機関でさえ、確実な答えは持っていない。

**でも、本当にそうなのか。「無理」と言われている境界線はどこに引かれているのか。**

論文では理由が示されている。けれど現代の AI で実装して、過去データと公開リソースで体系的に試した記録は、特に日本語ではほぼ存在しません。

そこを埋めたい。それがこの公開プロジェクトの動機です。

毎週水曜に検証記事を公開し、すべてのコードをここに置きます。**結果が良くても悪くても、失敗を含めて全部記録**します。

---

## 配信先

| プラットフォーム | リンク | 頻度 |
|--------------|-----|------|
| note (記事本編) | [@ai_compass_media](https://note.com/ai_compass_media) | 毎週水曜 12:00 |
| X (速報・補足) | [@ぬるぽん](https://x.com/) | 日次 |
| GitHub (コード) | [このリポジトリ](https://github.com/nullponull/aiquant-lab) | 記事公開と同時 |

---

## 6 つの壁

AI で市場予測ができないと言われる理由は、6 つの壁に整理できます：

| # | 壁 | 内容 |
|---|---|------|
| 1 | **再帰性** | 戦略は知られた瞬間に死ぬ |
| 2 | **非定常性** | 過去 ≠ 未来の統計分布 |
| 3 | **グッドハート** | 最適化が意味を失う |
| 4 | **複雑系** | カオスで予測不可 |
| 5 | **ファットテール** | 過去にない事象 |
| 6 | **自己言及性** | 価格が自分自身を含む |

各壁に対して、1 つ以上の実験で実装で挑戦します。

---

## 連載スケジュール

| 回 | タイトル | 検証する壁 | ステータス |
|----|--------|---------|-------|
| #0 | マニフェスト | 全体 | ✅ 公開済み |
| #1 | 「3 週間で 4% 勝った」戦略を 10 年遡る | 非定常性 | ✅ 公開済み |
| #2 | LLM 議論型エージェントは有効か | 自己言及性 | ✅ 公開済み |
| #3 | 100 万円× 100 戦略の並列稼働 | グッドハート | 🔄 進行中 |
| #4 | ロボアド 5 社の戦略を解剖 | 再帰性 | 📅 予定 |
| #5 | コロナ暴落を AI は検知できたか | ファットテール | 📅 予定 |
| #6 | 「AI で○億円」系商材の数学的検証 | グッドハート | 📅 予定 |
| #7 | Claude Code 投資ボット 1 ヶ月運用結果 | 複雑系 | 📅 予定 |
| #8 | 1 ヶ月総括 | 統合考察 | 📅 予定 |

---

## クイックスタート

### 環境構築

[uv](https://github.com/astral-sh/uv) を使った Python 3.13 環境：

```bash
git clone https://github.com/nullponull/aiquant-lab
cd aiquant-lab
uv sync
```

### 第 1 回の実験を再現する

10 年バックテストを実行（API キー不要、yfinance のみ使用）：

```bash
uv run python code/backtest_001.py
```

期待される結果：
- ツイート戦略（70/30）: CAGR 13.29%
- SPY バイアンドホールド: CAGR 13.20%
- 差: 0.09%（誤差レベル）

### 第 2 回の実験を再現する

LLM 議論型エージェントの実験には Anthropic API キーが必要：

```bash
# 1. https://console.anthropic.com で API キーを取得（$5 程度の入金）
export ANTHROPIC_API_KEY=sk-ant-...

# 2. 実験を実行（30 イベント、約 $0.50-1.00、5-10 分）
uv run python code/experiments/run_episode2.py --n-events 30

# Claude CLI による拒否を再現したい場合（要 Claude Code CLI）
uv run python code/experiments/demonstrate_claude_cli_wall.py
```

API キーがなくても、Mock LLM でフレームワークの動作確認はできます：

```bash
uv run python code/experiments/run_episode2.py --mock --n-events 30
```

---

## ディレクトリ構造

```
aiquant-lab/
├── articles/         # note 記事の本文（連載各回）
│   ├── 000_manifesto.md
│   ├── 001_3weeks_4percent_backtest_note.md
│   └── 002_llm_debate_vs_evaluator.md
├── code/
│   ├── agents/       # LLM エージェント実装
│   │   ├── base.py
│   │   ├── llm_client.py    # Anthropic API + Claude CLI + Mock
│   │   ├── solo.py
│   │   ├── debate.py
│   │   ├── evaluator.py
│   │   └── baseline.py
│   ├── experiments/
│   │   ├── run_episode2.py
│   │   └── demonstrate_claude_cli_wall.py
│   └── backtest_001.py
├── promo/            # X 投稿テンプレ集
├── docs/             # 設計ドキュメント
├── legal/            # 免責事項テンプレ
├── results/          # 検証結果（JSON, CSV）
├── POSTING_STRATEGY.md
├── pyproject.toml
└── README.md
```

---

## 第 1 回の主要結果

「3 週間で +4% 勝った」AI 自動売買戦略を 10 年バックテストした結果：

| 戦略 | CAGR | シャープレシオ | 最大 DD |
|------|------|------------|-------|
| ツイート戦略（70/30） | 13.29% | 0.83 | -32.3% |
| SPY バイアンドホールド | 13.20% | 0.81 | -33.7% |
| NOBL 単独 | 9.99% | 0.67 | -35.4% |

**結論**: 凝った戦略を組んでも SPY 放置と差はほぼゼロ。3 週間で +4% 以上のリターンが起きる確率は 13.2%（ノイズの範囲）。

詳細: [articles/001_3weeks_4percent_backtest_note.md](articles/001_3weeks_4percent_backtest_note.md)

---

## 第 2 回の主要発見

LLM 議論型エージェントを実装で検証しようとして、**予想外の壁にぶつかりました**：

> Claude CLI に投資判断を聞いたら「software engineering assistant の範囲外」と拒否された。

これを「**規範的拒否（第 7 の壁）**」として連載に追加。技術的な壁ではなく、社会的・規範的な壁。

詳細: [articles/002_llm_debate_vs_evaluator.md](articles/002_llm_debate_vs_evaluator.md)

再現コード: [code/experiments/demonstrate_claude_cli_wall.py](code/experiments/demonstrate_claude_cli_wall.py)

---

## 技術スタック

- **言語**: Python 3.13
- **依存管理**: [uv](https://github.com/astral-sh/uv)
- **データ**: yfinance, pandas, numpy
- **LLM**: Anthropic Claude API（公開実験用）/ Claude CLI（開発用） / Mock（テスト用）
- **イベントデータ**: [WORLDmonitor](https://github.com/koala73/worldmonitor)（第 5 回以降で使用予定）

---

## なぜ取り組むのか

AI エージェントの設計を仕事にしていて、毎日のように「AI で何ができて何ができないか」と向き合っています。「市場予測」だけは長く「無理」と言われ続けている領域。その境界線がどこにあるのか、自分の手で確かめたくなりました。

完全な勝ちパターンを見つけるのが目的ではありません。**現在の AI で「どこまで」は可能で、「どこから」は不可能なのかの境界線を、実装でマッピングする**ことが目的です。

その境界線の地図ができれば、AI 投資に取り組む人すべてが、自分のリソースをどこに集中すべきか判断できるようになります。

**好奇心が先、収益は後。** この順序を守ります。

---

## 貢献・フィードバック

連載は AIコンパスのオウンドメディアで進めますが、コードに関するフィードバックは歓迎します：

- **Issue**: 実装の問題、追加実験のリクエスト、再現性の確認
- **Pull Request**: 既存実験への改良、新しい検証ロジック
- **Discussion**: 連載のテーマや 6 つの壁に対する議論

X (@ぬるぽん) でも各回の反応を歓迎します。

---

## ライセンス

ソースコード: MIT License

記事本文 (`articles/`): CC BY-NC-SA 4.0（非商用利用、改変時は同条件で）

---

## 免責事項

本プロジェクトは**教育・研究目的の情報提供**であり、投資助言ではありません。記載の数値はすべて公開市場データに基づくシミュレーション結果であり、実際の取引は行っていません。過去の結果は将来の成果を保証しません。

本プロジェクトは金融商品取引法に定める投資助言・代理業、投資運用業のいずれにも該当しません。特定の金融商品の購入・売却を推奨するものではありません。

特定のツイート・発信者を批判する意図はありません。検証対象は匿名化のうえ、学習素材として扱っています。

詳細は [legal/disclaimer.md](legal/disclaimer.md) を参照してください。

---

**著者**: [@ぬるぽん](https://x.com/) / [@ai_compass_media](https://note.com/ai_compass_media)
