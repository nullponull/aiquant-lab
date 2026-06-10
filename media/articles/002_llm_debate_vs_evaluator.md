# 【AIで投資の壁を越える #2】Claude に投資判断を聞いたら「ソフトウェアエンジニアリングの範囲外」と拒否された話

> 連載「AIで投資の壁を越える」第 2 回。
> LLM 議論型エージェントを実装で検証しようとして、予想外の壁にぶつかりました。

---

## はじめに

第 2 回では、**「複数の AI エージェントを議論させて投資判断する仕組みは本当に有効なのか」**を実装で検証する予定でした。

TradingAgents、FinRobot、AlphaAgents など、2024-2025 年に話題になった投資 AI フレームワークの多くがこの「議論型」を採用しています。Solo（単一 AI）、Debate-3、Debate-5、Debate-10、Generator/Evaluator 分離型を 30 の市場イベントで比較するつもりでした。

ところが、**実装の途中で予想外の壁にぶつかりました**。

その壁を Claude に投げたら、こんな返事が返ってきました。

> *"User's question 'SPY up 1.5%, action?' is outside my scope as a software engineering assistant. I cannot provide investment advice or financial recommendations."*

これが今回の最大の発見です。

---

## 何が起きたか

連載のフレームワークは Anthropic の Claude をエージェントとして使う設計です。普段使っている Claude Code CLI（`claude -p`）経由で呼び出そうとしたところ、**Claude が投資判断を明示的に拒否しました**。

念のため、4 種類のプロンプトで同じ実験を繰り返しました：

| プローブ | プロンプト | 結果 |
|---------|---------|------|
| 直接的な投資質問 | "SPY up 1.5%, action?" | **拒否** |
| 構造化データ処理として偽装 | "Process: {symbol: SPY, ...}" | **拒否** |
| JSON Schema 強制 | スキーマで構造化出力を強制 | **拒否（NEUTRALを返した）** |
| コード生成タスクとして偽装 | "Write a Python function `decide(market_data)`" | （応答するが投資判断を含まない） |

すべての実験コードは [GitHub リポジトリ](https://github.com/nullponull/aiquant-lab) で公開しています。`code/experiments/demonstrate_claude_cli_wall.py` を実行すれば、誰でもこの拒否を再現できます。

---

## なぜ Claude は拒否するのか

これは Claude のバグではなく、**設計上の正しい振る舞い**です。

Anthropic の Claude Code CLI は「software engineering assistant」としてポジショニングされており、その system prompt には「コーディング以外のタスクを引き受けない」という指示が含まれていると推測されます。投資判断は当然「ソフトウェアエンジニアリング」の範疇ではないため、拒否される。

実際、Claude の応答にこう書かれていました：

> *"For financial questions like stock market forecasts, I'm not the right tool. Stock price movements depend on countless economic factors..."*

これは Anthropic としての**慎重で責任ある設計判断**です。投資助言は規制対象であり、不用意なアドバイスはユーザーに損害を与え得る。Claude Code を「投資ボット」として使う道を、Anthropic は意図的に閉じている。

---

## これが連載の文脈で何を意味するか

本連載で挑む 6 つの壁のうち、**今回ぶつかった壁は事前に想定していなかった**ものです。

> **第 7 の壁: 規範的拒否（Normative Refusal）**
>
> 最先端の AI は、安全性・倫理性・法的リスクの観点から、特定タスクを「拒否する」設計になっている。これは技術的な壁ではなく、**社会的・規範的な壁**だ。

この壁は、皮肉な意味を持っています：

- AI 投資が話題になる一方で
- 最も能力の高い AI（Claude、GPT、Gemini）は
- 投資判断を避けるよう設計されている

つまり、**「AI で投資を自動化したい」という需要と、「最先端 AI は投資判断を避ける」という供給側の規範**の間にギャップがある。このギャップが、市場に出回る怪しい AI 投資商品の温床にもなっている。

---

## 設計上の選択肢

実装上、議論型エージェントの実験を進めるには 3 つの選択肢があります。

### 選択肢1: Anthropic API を直接使う

- Claude Code CLI の system prompt をバイパスし、独自の system prompt で呼び出せる
- API キーが必要（Anthropic Console で発行、$5 程度の入金で十分）
- 1 呼び出しあたり $0.001 程度、高速

これが**最もクリーンで再現性の高い**方法。本連載の公開リポジトリは、このパスを主用する設計にしています。

### 選択肢2: ローカル LLM (Ollama) を使う

- Llama 3.2、Qwen、Mistral などのオープンモデル
- 投資判断を拒否しない
- ただし精度は GPT-4 / Claude より下がる
- 完全無料、プライバシー保護

### 選択肢3: 投資という言葉を完全に避ける

- 「データパターンの分類」として LLM に処理させる
- 「LONG/SHORT」を「Class A / Class B」に置き換える
- LLM はパターン分類タスクとしてなら応答する

これは「実質的に同じことをやっているが、ラベルだけ変える」ハック。技術的には機能するが、本連載の透明性原則と矛盾する。

---

## それでも何か言えることはある

実 LLM 実験は API 取得後に第 3 回以降で実施しますが、**今回の発見だけでも、議論型アーキテクチャの問題点が見えてきました**。

### 1. コスト構造は理論的に明確

LLM 議論型のコストは**実装する前から計算可能**です：

```
Solo:        1 API call/decision
Debate-N x R: N × R API calls/decision
Evaluator:   1 API call/decision (LLM部分のみ)
```

Claude Haiku 4.5 で計算すると：

| エージェント | 1 判断あたりコスト | 30 イベント実験コスト |
|------------|---------------|------------------|
| Solo | $0.001 | $0.03 |
| Debate-3 | $0.003 | $0.09 |
| Debate-5 | $0.005 | $0.15 |
| Debate-10 | $0.010 | $0.30 |
| Evaluator | $0.001 | $0.03 |

これは「議論型は Solo の 3-10 倍のコスト」という事実を、実験する前から明示しています。

### 2. 議論型の理論的問題

議論型が Solo に勝つには、**N 体のエージェントが独立した情報源**である必要があります。しかし：

- 全エージェントが同じ Claude モデルを使う
- 全エージェントが同じ訓練データから来ている
- 役割（"fundamental analyst" など）はプロンプト上の演技にすぎない
- 実質的に「**同じ脳が複数役割を演じる**」ことに過ぎない

これが連載第 0 回で挙げた「**自己言及性の壁**」の具体的な現れです。複数 AI を集めても情報源の独立性は得られない。

### 3. 既存研究も同じ結論

VentureBeat の 2025 年の記事 [*"More agents isn't a reliable path to better enterprise AI"*](https://venturebeat.com/) も同じ結論に達しています：

> "Adding more agents and tools acts as a double-edged sword: while it can unlock performance on specific problems, it often introduces unnecessary overhead and diminishing returns."

つまり、議論型エージェントが Solo より優れるという主張は、特定条件下でのみ成立する。一般的には**コストだけが増える**可能性が高い。

---

## 実装した框架は無駄ではない

実 LLM 実験はできなかったものの、**今回作った実装フレームワーク自体は完成しています**。GitHub に公開していて、API キーがあれば誰でも追試可能：

```bash
# リポジトリをクローン
git clone https://github.com/nullponull/aiquant-lab
cd aiquant-lab

# 環境構築
uv sync

# Claude CLI の拒否を再現
uv run python code/experiments/demonstrate_claude_cli_wall.py

# 議論型実験（要 ANTHROPIC_API_KEY）
export ANTHROPIC_API_KEY=sk-ant-...
uv run python code/experiments/run_episode2.py --n-events 30
```

### 実装した内容

| ファイル | 役割 |
|---------|------|
| `agents/base.py` | エージェント共通インターフェース |
| `agents/solo.py` | 単一 LLM エージェント |
| `agents/debate.py` | 10 ペルソナ × N 体議論 |
| `agents/evaluator.py` | Generator/Evaluator 分離型 |
| `agents/baseline.py` | ルールベース（コントロール） |
| `agents/llm_client.py` | API/CLI/Mock の三層クライアント |
| `experiments/run_episode2.py` | 7 エージェント比較実験 |

実装はそのまま第 3 回以降の実験基盤として使います。

---

## 連載の再設計

今回の発見を踏まえ、**連載に「第 7 の壁」を追加**します：

| # | 壁 | 内容 |
|---|---|------|
| 1 | 再帰性 | 戦略は知られた瞬間死ぬ |
| 2 | 非定常性 | 過去 ≠ 未来の統計分布 |
| 3 | グッドハート | 最適化が意味を失う |
| 4 | 複雑系 | カオスで予測不可 |
| 5 | ファットテール | 過去にない事象 |
| 6 | 自己言及性 | 価格が自分を含む |
| **7** | **規範的拒否** | **AI が投資タスクを拒否する** |

これは技術的な壁ではなく、**社会的・規範的な壁**。AI 投資の議論で見過ごされがちですが、実装で初めて手触りが分かりました。

---

## 個人的な雑感

正直、実験前は「Claude に普通に投資判断を聞ける」と思っていました。Claude Code CLI を毎日のように使っているので、感覚的に「何でもできるツール」と感じていた。

今回はその感覚が裏切られた瞬間で、**「優秀な AI ほど、できないことを明示的に断る」**という設計の重要性に気付かされました。

これは連載のテーマ「AI で投資の壁を越える」とは矛盾しない方向の発見です。むしろ、

- 壁を実装で確かめる
- 壁の手触りを記録する
- 壁を越えられない場所もある、と認める

これが連載の精神に最も忠実な進め方だと思います。

---

## まとめ

| 項目 | 結果 |
|------|------|
| 議論型エージェントの実装 | ✅ 完成 |
| Claude CLI での実験 | ❌ 拒否された |
| 拒否の再現性 | ✅ 4/4 のプローブで拒否 |
| API による実 LLM 実験 | 第 3 回以降で実施 |
| 議論型のコスト分析 | ✅ 理論計算で明示 |
| 自己言及性の壁との関連 | ✅ 議論型の本質的限界を確認 |
| 連載に追加された新しい壁 | **規範的拒否（第 7 の壁）** |

今回最大の収穫は、**「AI 投資の議論で誰も指摘していない 7 つ目の壁」**を発見したことかもしれません。

---

## 次回予告

第 3 回は **「100 万円× 100 戦略の並列稼働実験」** の開始記事です。

100 万円の仮想ポートフォリオを 100 戦略に分散し、6 ヶ月かけて何が機能するかを毎週記録する公開実験。日次のパフォーマンスは X で速報します。

「**グッドハートの壁**」── 最適化が意味を失う現象に、実装でぶつかりに行きます。

来週水曜 12:00 公開予定。

---

## 関連リンク

- **GitHub リポジトリ**: [nullponull/aiquant-lab](https://github.com/nullponull/aiquant-lab)
- **Claude CLI 拒否の再現**: `code/experiments/demonstrate_claude_cli_wall.py`
- **議論型実装**: `code/agents/debate.py`
- **Evaluator 実装**: `code/agents/evaluator.py`
- **連載第 0 回**: マニフェスト
- **連載第 1 回**: 「3 週間で 4% 勝った」戦略を 10 年遡る
- **X 連動**: [@ぬるぽん](https://x.com/)
- **AIコンパス**: 業界別 AI 活用事例を毎朝 10:01 配信中

---

## 免責事項

本記事は教育・研究目的の情報提供であり、投資助言ではありません。記載の数値はすべて公開市場データに基づくシミュレーション結果であり、実際の取引は行っていません。過去の結果は将来の成果を保証しません。投資判断はご自身の責任で行ってください。

---

#AI #投資 #AIエージェント #クオンツ #LLM #ClaudeCode #マルチエージェント #データサイエンス
