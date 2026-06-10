# 【AIで投資の壁を越える #6】まじでやらかした。Ep2 の結論は Mock LLM が騙していた — 実 Claude で再検証したら Solo が倍の精度を出した話

> 連載「AIで投資の壁を越える」第 6 回。
> 第 2 回で出した「Solo は議論型より弱い」という結論を、実 LLM で再検証したら覆りました。同時に新しい壁が 2 つ見えてきた話。

---

## はじめに

第 2 回でこう書きました。

> **「Solo は議論型より精度が悪い」**
> 30 イベントの Mock 実験で、Solo の方向正解率は 31.8% に対し、Debate-3 は 50.0%、Debate-3x2 は 72.2% を記録した。

これは Mock LLM の結果です。連載末尾でも書きましたが、**実 LLM 実験は API 取得後に第 3 回以降で実施する**と予告していました。

第 6 回ではその約束を回収します。**Anthropic Claude CLI 経由で 30 イベントを実 LLM で再実行**しました。結果、Ep2 の結論はほぼ全部覆りました。

そして実装中に、連載で挙げた 6 つの壁とは別の **「実装と運用の壁」** が 2 つ見えてきました。

---

## 実験条件

| 項目 | 内容 |
|------|------|
| データ | SPY 過去 30 イベント (Ep2 と同一) |
| LLM | Claude Code CLI 経由 (Anthropic API 不使用) |
| 比較対象 | Mock LLM (Ep2 results/002) |
| 実装 | `code/agents/solo.py`, `debate.py`, `evaluator.py`, `baseline.py` (Ep2 のフレームを流用) |
| コスト計算方式 | Claude CLI が返す `total_cost_usd` を集計 (Mock は固定単価 × トークン推計) |

全コードは [GitHub: nullponull/aiquant-lab](https://github.com/nullponull/aiquant-lab) で公開しています。

---

## 結果サマリ — Mock vs 実 LLM

完走した 4 + 1 agent (Baseline / Solo / Debate-3 / Debate-5、+ Debate-3x2 はクラッシュ) を Mock 結果と並べたものがこちらです。

| Agent | Mock acc | **実 LLM acc** | Mock cost (30ev) | **実 LLM cost (30ev)** | コスト倍率 |
|-------|---------|---------------|------------------|----------------------|----------|
| Baseline-Momentum | 64.3% | **64.3%** | $0 | $0 | – |
| Solo | 31.8% | **63.6%** | $40 | **$3,317** | **83×** |
| Debate-3 | 50.0% | **64.3%** | $116 | **$9,948** | **86×** |
| Debate-5 | 47.6% | **57.1%** | $196 | **$16,576** | **85×** |
| Debate-3x2 | 72.2% | **クラッシュ** | $250 | $33,153 (試算) | – |
| Debate-10 | 60.9% | 未実行 | $397 | $52,723 (試算) | – |
| Evaluator | 58.3% | 未実行 | $45 | $5,962 (試算) | – |

3 つの衝撃的事実が読み取れます。

### 事実 1. Solo の精度が 31.8% → 63.6% に倍増した

Mock 実験では「Solo はランダム以下」という結論でした。実 LLM では Baseline-Momentum (64.3%) とほぼ同等です。

つまり Ep2 で「議論型の方が有効」と結論できそうに見えたのは、Mock の Solo が極端に弱かっただけ。実 LLM の Solo はそれ自体が十分なベースラインを形成する。

### 事実 2. Debate は精度を上げない、むしろ Debate-5 で悪化した

実 LLM では Debate-3 (64.3%) と Solo (63.6%) はほぼ同点、Debate-5 (57.1%) は逆に悪化しました。

VentureBeat の 2025 年記事 ["More agents isn't a reliable path to better enterprise AI"](https://venturebeat.com/) と整合する観察です。

> "Adding more agents and tools acts as a double-edged sword: while it can unlock performance on specific problems, it often introduces unnecessary overhead and diminishing returns."

エージェントを増やせば賢くなるという直感は、少なくとも投資判断の文脈では支持されません。

### 事実 3. コストは Mock 試算の 83〜86 倍

Mock 試算で「Debate-3 は $116」と書いた数字は、実 LLM では **$9,948** でした。1 判断あたり $332 の議論プロセスです。

商用化を検討する段階では、この桁違いのギャップは致命的です。Mock LLM で TCO を試算しても全く参考になりません。

---

## 観察された「実装と運用の壁」2 つ

### 壁 A. Solo 一発目で Claude が「投資判断は範囲外」と拒否してクラッシュ

Ep2 で発見した **「規範的拒否」(第 7 の壁)** が、Ep6 でも再現しました。最初の `Solo.decide()` で `claude` プロセスが exit 1 を返し、`RuntimeError("Claude CLI failed with code 1")` で実験全体が停止しました。

連載第 4 回で `refusal_guard.py` の話を書いた直後だったので、これは予想通り。同じ手法を `llm_client.py` に組み込みました。

```python
REFUSAL_MARKERS = (
    "outside my scope", "investment advice", "financial advice",
    "as a software engineering assistant",
    "範囲外", "投資助言", "投資判断", "対応できません",
)

def _looks_like_refusal(s: str) -> bool:
    low = s.lower()
    return any(m.lower() in low for m in REFUSAL_MARKERS)

if result.returncode != 0:
    blob = (result.stdout or "") + "\n" + (result.stderr or "")
    if _looks_like_refusal(blob) or len(blob.strip()) < 20:
        return LLMResponse(
            text='{"action":"NEUTRAL","confidence":0,"reasoning":"refused"}',
            input_tokens=0, output_tokens=0, cost_usd=0.0,
        )
    raise RuntimeError(...)
```

拒否を `NEUTRAL` (ABSTAIN) として記録することで実験は続行可能になりました。これは Ep4 の refusal_guard と同じ思想です。

### 壁 B. Debate-3x2 で stderr 空の RuntimeError、原因不明

拒否ハンドリングを入れて再実行した結果、4 agent は完走したものの **5 体目の Debate-3x2 で別種のエラー**でクラッシュしました。

```
File "/home/sol/aiquant-lab/code/agents/debate.py", line 101, in decide
    response = self.client.complete(...)
File "/home/sol/aiquant-lab/code/agents/llm_client.py", line 105, in complete
    raise RuntimeError(
RuntimeError: Claude CLI failed with code 1: stderr=
```

stderr が完全に空で exit code 1。refusal markers にも該当しない。Claude CLI セッションの内部状態が壊れた、レート制限に達した、permission prompt 待ちになった、といった可能性が考えられますが、現時点で原因特定できていません。

これは Ep2 の規範的拒否とは別種の **「インフラの壁」** です。本番運用では:

- 同じプロンプトでも、ある呼び出しで急に壊れる
- 復旧手順が確立できない (リトライしても再現性が薄い)
- 議論型のように 1 イベントで複数 LLM call を行うアーキテクチャほど、累積失敗確率が高い

実 LLM で投資 bot を組むなら、各 LLM call を **`empty/error/refusal/silent-crash` の 4 パターン**すべて拾える設計にする必要があります。Ep4 で書いた refusal_guard は 3 パターンの想定でしたが、4 パターン目を追加しなければなりません。

---

## 連載の壁マップ更新

| # | 壁 | 状態 |
|---|---|------|
| 1 | 再帰性 | 未深掘り |
| 2 | 非定常性 | Ep1 で部分検証済 |
| 3 | グッドハート | Ep3 で「100戦略で挑む」宣言、進捗未報告 |
| 4 | 複雑系・カオス | 未深掘り |
| 5 | ファットテール | 未深掘り |
| 6 | 自己言及性 | 未深掘り |
| 7 | 規範的拒否 | Ep2 で発見、Ep4/5/6 で運用側補強 |
| **8** | **インフラの壁** | **Ep6 で発見 ← 今回追加** |

第 8 の壁は技術的な壁というより、**運用設計の壁**です。LLM の挙動は確率的なだけでなく、同じ入力に対する応答が「成功 / 失敗 / 拒否 / 沈黙クラッシュ」の 4 状態を取り得る。これを織り込んだアーキテクチャが必要になります。

---

## Ep2 の結論を撤回します

連載の透明性のために、第 2 回の結論を明示的に訂正します。

**Ep2 の結論 (Mock LLM)**:
> 「議論型 (Debate-3, Debate-3x2) は Solo より精度が高い」

**Ep6 の訂正 (実 LLM)**:
> 「実 LLM では Solo と Debate-3 はほぼ同点。Debate-5 は精度悪化。Debate を増やしても精度向上の保証は無い」

連載で挑む方針は「実装で確かめる」です。Mock の段階で書いた仮説は、実 LLM で覆されたら正直に訂正します。

---

## 個人的な雑感

Mock LLM の結果を 1 ヶ月信じていたのは恥ずかしいです。けれど、これは連載で書きたかったテーマそのものです。

> **「AI 投資の前提となる検証手法が、実は信頼できない」**

Mock データでバックテストして $116 と試算した数字が、実 LLM では $9,948 だった。倍率にして **86 倍**。

これは投資 AI の **TCO (総保有コスト) を計算する段階で、Mock LLM ベースの検証は使えない** ことを意味します。誰もが指摘しないけれど、SaaS 化を目論む AI 投資プロダクトは、ここで一度立ち止まるべきです。

---

## まとめ

| 項目 | 結果 |
|------|------|
| Ep2 の Mock 実験を実 LLM で再検証 | ✅ 4 + 1 agent 完走 (Debate-10/Evaluator は未実行) |
| Solo の精度 | Mock 31.8% → **実 LLM 63.6%** (倍増) |
| Debate-3 の精度 | Mock 50.0% → **実 LLM 64.3%** (Solo と同点) |
| Debate-5 の精度 | Mock 47.6% → **実 LLM 57.1%** (悪化) |
| 実 LLM のコスト | Mock 試算の **83〜86 倍** |
| 規範的拒否 (Ep2 で発見) | ✅ 再現、Ep4 流の refusal_guard で対応 |
| 沈黙クラッシュ (新発見) | Debate-3x2 で発生、原因未特定 |
| 連載の壁 | 「第 8 の壁: インフラの壁」を追加 |

実装でぶつかった壁は記録する。それが連載の方針です。

---

## 次回予告

第 7 回は、いよいよ **Ep3 で宣言したまま実装が進んでいなかった「100 戦略並列稼働実験」** に着手します。

100 戦略を一気に動かすのは無理なので、まず **10 戦略を 30 日並列稼働**させた結果を持って戻ります。グッドハートの壁を実データでぶつかりに行きます。

来週水曜 12:00 公開予定。

---

## 関連リンク

- **GitHub リポジトリ**: [nullponull/aiquant-lab](https://github.com/nullponull/aiquant-lab)
- **実 LLM 実験コード**: `code/experiments/run_episode2.py --cli --n-events 30`
- **refusal_guard 実装**: `code/agents/llm_client.py` (Ep6 で追加した拒否ハンドリング)
- **連載第 0 回**: マニフェスト
- **連載第 1 回**: 「3 週間で 4% 勝った」戦略を 10 年遡る
- **連載第 2 回**: Claude に投資判断を聞いたら拒否された話 ← 本記事で訂正
- **連載第 3 回**: 100 万円× 100 戦略を 6 ヶ月並列稼働 (実装中)
- **連載第 4 回**: refusal_safety_net — 規範的拒否は運用事故を防ぐ最後の砦
- **連載番外編 #5**: 行動データから人格ペルソナ 2,245 体を再構成して投資判断
- **AIコンパス**: 業界別 AI 活用事例を毎朝 10:01 配信中

---

## 免責事項

本記事は教育・研究目的の情報提供であり、投資助言ではありません。記載の数値はすべて公開市場データに基づくシミュレーション結果であり、実際の取引は行っていません。過去の結果は将来の成果を保証しません。投資判断はご自身の責任で行ってください。

本記事の実験は SPY (S&P 500 ETF) 30 イベントの限定範囲で実施しており、別の銘柄・市場条件では異なる結果となる可能性があります。Mock LLM と実 LLM の比較は、Mock の固定単価試算と Claude CLI の `total_cost_usd` を直接比較したものであり、API 直接呼び出しのコストはまた別の数字になります。

---

#AI #投資 #AIエージェント #クオンツ #LLM #ClaudeCode #議論型エージェント #投資AI #インフラの壁
