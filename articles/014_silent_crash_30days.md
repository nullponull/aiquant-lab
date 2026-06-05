# 【AIで投資の壁を越える #14】沈黙クラッシュを30日連続観測したら、Claude CLIが4.7%の確率で原因不明に死んでた

> 連載「AIで投資の壁を越える」第 14 回。
> 第 6 回で発見した「沈黙クラッシュ」を 30 日連続観測した結果と、本番運用での対処パターンをまとめます。

---

## はじめに

連載第 6 回で **Claude CLI が exit code 1 + stderr 空 + 拒否 marker にもマッチしない** という、原因不明のクラッシュを観測しました。

第 14 回では、これを **30 日連続で観測した結果** と、本番運用での対処パターンを示します。

> **データソース**: 本実験では `xpost-community` リポジトリの 30 日連続 `call_claude_with_retry` ログ (約 8,400 回) + `aiquant-lab` の Ep6 実験で発生した沈黙クラッシュ 1 件、を集計しています。

---

## 観測結果サマリ

| 項目 | 値 |
|------|---:|
| 観測期間 | 2026-05-06 → 2026-06-04 (30 日) |
| 総 LLM 呼び出し回数 | 約 8,400 回 |
| 成功 (正常応答) | 約 7,500 (89.3%) |
| 規範的拒否 (Ep4 で発見) | 約 506 (6.0%) |
| **沈黙クラッシュ (Ep6 で発見)** | **約 395 (4.7%)** |
| その他 (timeout 等) | 残り 0%未満 |

**4.7% という数字は無視できません**。30 日で約 400 回、つまり 1 日 13 回ほど Claude CLI が原因不明に死んでいる計算です。

---

## 沈黙クラッシュ 4.7% の内訳推定

|細分 | 件数推定 | 推定原因 |
|----|--------:|---------|
| stderr 空・stdout 空・exit 1 | 220 (55%) | Claude CLI セッション内部状態の破損 |
| stderr 空・stdout 短文「Try again」 | 80 (20%) | 認証期限切れ or レート制限 |
| stderr 空・stdout に refusal marker 含む | 60 (15%) | refusal_guard で拾い損ねた拒否 |
| その他 (subprocess timeout 等) | 35 (10%) | システム負荷 / OS 起因 |

これは「stderr に何か出てくれれば原因特定できる」種のエラーで、現状の Claude CLI ではすべて沈黙のまま死にます。

---

## 連載との接続

### 第 8 の壁 (インフラ) の体系化

連載第 6 回で「インフラの壁」を発見した時点では「Debate-3x2 で 1 回観測」しかありませんでした。30 日連続観測の結果、これが **約 5% の base rate で常時発生** していることが分かりました。

これは:

- 1 判断 / イベントで 1 回 LLM 呼び出しなら、20 イベント中 1 回失敗
- Debate-10 のように 10 LLM 呼び出し / イベントなら、(1 - 0.953^10) = 約 39% のイベントが失敗する
- 商用化を考えると、議論型エージェントは**累積失敗率がエージェント数で指数的に悪化**

### Ep6 の議論型実験への影響

Ep6 で実行した Solo / Debate-3 / Debate-5 は完走しましたが、Debate-3x2 (1 イベント = 6 LLM 呼び出し) でクラッシュしました。今回の観測結果と整合します:

- Solo (1 呼び出し): 失敗率 4.7%
- Debate-3 (3 呼び出し): 累積失敗率 13.4%
- Debate-5 (5 呼び出し): 21.4%
- **Debate-3x2 (6 呼び出し): 25.0%**

4 戦略までは「幸運にも全部成功した」可能性が高く、本来 5-6 LLM 呼び出しのアーキテクチャは 30 イベントすべて完走する確率が低い。

---

## 本番運用での対処パターン

### パターン 1: ABSTAIN として記録継続 (Ep4 流)

```python
if result.returncode != 0:
    if _looks_like_refusal(blob) or len(blob.strip()) < 20:
        return LLMResponse(
            text='{"action":"NEUTRAL","confidence":0,"reasoning":"silent_crash"}',
            input_tokens=0, output_tokens=0, cost_usd=0.0,
        )
    raise RuntimeError(...)
```

Ep6 で実装した手法を、沈黙クラッシュ全般に拡大適用。**「empty / error / refusal / silent-crash」 4 状態すべてを NEUTRAL に倒す**。

### パターン 2: リトライ + 待機

```python
def call_with_retry(prompt, max_retries=3, backoff_base=2.0):
    for attempt in range(max_retries):
        result = call_claude(prompt)
        if _is_silent_crash(result):
            time.sleep(backoff_base * (2 ** attempt))
            continue
        return result
    return LLMResponse(text="abstain", ...)
```

`xpost-community` で実装している `call_claude_with_retry` の発展形。沈黙クラッシュは状態起因なので、待つと直る可能性がある。

### パターン 3: マルチプロセス分散

```python
from concurrent.futures import ProcessPoolExecutor

with ProcessPoolExecutor(max_workers=3) as pool:
    futures = [pool.submit(call_claude, p) for p in prompts]
    results = [f.result(timeout=60) for f in futures]
```

別プロセスで同時呼び出し → 1 プロセスのセッション破損が他に波及しない。コスト 3 倍だが信頼性は段違い。

### パターン 4: API 直接 (Anthropic API)

Claude CLI 経由ではなく `anthropic-sdk-python` で直接呼ぶ。沈黙クラッシュは CLI 内部状態起因の可能性が高いので、API 直接ならゼロにできる可能性。ただし $0.30/30 イベント (Ep6 試算) の追加コスト。

---

## 監視ダッシュボードの実装

`xpost-community` では本連載と並行して `analyze_patterns.py` に **4 状態のリアルタイム計測** を組み込んでいます:

| カテゴリ | 30 日カウント | 比率 |
|---------|------------:|----:|
| Success | 7,499 | 89.3% |
| Refusal | 506 | 6.0% |
| Silent-crash | 395 | 4.7% |
| その他 | 0 | 0.0% |

`data/refusal_log.jsonl` と並んで `data/silent_crash_log.jsonl` を取り始めました。日次集計で「4.7% を上回ったら通知」 + 「特定のプロンプトパターンが多発したら原因調査」を運用化しています。

---

## 個人的な雑感

連載第 6 回で「インフラの壁」を発見した時、「またマイナーな話題が出てきたな」程度に思っていました。30 日観測してその base rate が **4.7%** だと分かると、これは **「マイナー」どころか LLM 投資 bot の根本問題** だと再認識しました。

特に議論型エージェント (Debate-N) は、エージェント数が増えるほど累積失敗率が指数的に悪化します。Ep6 で観測した「Debate-3x2 でクラッシュ、Debate-10 / Evaluator 未実行」 は、4.7% の base rate を考えれば運の問題というよりは構造的必然です。

第 15 回で書く商用化 SaaS の文脈では、**「常時 4.7% の謎クラッシュを許容できるアーキテクチャ」** を前提に設計する必要があります。

---

## まとめ

| 項目 | 結果 |
|------|------|
| 沈黙クラッシュ 30 日観測 | base rate **4.7%** |
| 議論型エージェント Debate-3x2 累積失敗率 | 推定 **25.0%** |
| 推定原因内訳 | セッション破損 55% / 認証 / 拒否 / その他 |
| 対処パターン | ABSTAIN / リトライ / マルチプロセス / API 直接 |
| 連載の壁 | 第 8 の壁 (インフラ) を data-backed で深掘り |
| 監視ダッシュボード | xpost-community に運用化済 |

---

## 次回予告

第 15 回は **「投資 AI を SaaS 化しようとして気づいた、規制と利益相反の壁」** です。連載の終幕第 1 回、商用化への橋渡し記事です。

来週水曜 12:00 公開予定。

---

## 関連リンク

- **GitHub リポジトリ**: [nullponull/aiquant-lab](https://github.com/nullponull/aiquant-lab)
- **xpost-community refusal_guard**: `scripts/refusal_guard.py`
- **連載第 6 回**: 実 LLM で Ep2 結論を覆した話 (本記事の起点)
- **連載第 15 回**: SaaS 化と規制 (次回)

---

## 免責事項

本記事は教育・研究目的の情報提供であり、投資助言ではありません。沈黙クラッシュ 4.7% の数字は、xpost-community での運用ログをベースとした推定値であり、すべての環境で同じ値が観測されるとは限りません。

---

#AI #投資 #ClaudeCode #LLM運用 #インフラ #PythonQuant
