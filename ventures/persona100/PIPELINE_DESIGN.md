# 番外編 #2「機関投資家ペルソナ100体」構築パイプライン設計書

> 作成日: 2026-05-17
> 公開ターゲット: 2026-06-04 (水) 12:00（番外編 #2 配信）
> 工数見積: 約2週間（5/17 着手 → 5/31 構築完了 → 6/4 公開）
> 対象: 著名投資家・機関投資家ペルソナ 100体

---

## 1. 設計原則

### 倫理・法務的境界線

- **公開情報のみ** を素材とする（書籍・公開IF・SEC公開資料・SNS）
- 個人特定情報は除去し、**「行動パターン・意思決定スタイル」** としてのみ保持
- 故人を含む場合は、本人が生前公表していた発言・著作の範囲内で構築
- 詐欺・違法行為で有罪確定した人物は対象外
- 「実投資家のプライベートデータ」は一切扱わない

### データ品質基準

- 1ペルソナあたり **公開情報3-5ソース** を必須引用
- 意思決定パターンの根拠は **検証可能** な発言・書籍ページ単位で記録
- 「型（archetype）」分類は本連載の6タイプ + 拡張型に揃える

---

## 2. パイプライン全体図

```
[Phase 1] Long list (100名選定)
    ↓ Agent生成 → longlist.yaml
[Phase 2] データ収集 (各ペルソナ3-5公開ソース)
    ↓ source_collector.py → sources/{id}_{name}.json
[Phase 3] テキスト抽出 + 要約
    ↓ text_extractor.py → extracted/{id}_text.md
[Phase 4] DD SDK 入力フォーマット変換
    ↓ persona_formatter.py → persona_inputs/{id}.json
[Phase 5] DD SDK で人格モデル構築
    ↓ build_personas.py → personas/{id}_persona.json
[Phase 6] 投資判断シミュレーション
    ↓ run_simulation.py → simulation_results/{id}.json
[Phase 7] 集計・分析・記事化
    ↓ analyze_results.py → article_data/wall7_part2.json
```

---

## 3. 各フェーズ詳細

### Phase 1: ロングリスト作成 (5/17-5/18)

**成果物**: `/home/sol/aiquant-lab/ventures/persona100/longlist.yaml`

100名の選定基準:
- Value投資家 15名 (バフェット、グレアム、リンチ等)
- Macro/Global 15名 (ソロス、ダリオ、ドラッケンミラー等)
- Quants 10名 (サイモンズ、シャノン、マンデルブロ等)
- Growth/Tech 10名 (カソン、ティール、ホロウィッツ等)
- Activist 8名 (アイカーン、アックマン等)
- Hedge fund 12名
- Distressed 8名 (クラーマン、テッパー等)
- 日本人 10名 (村上、テスタ等)
- Crypto 5名
- Academic 7名

### Phase 2: データ収集 (5/19-5/21)

**スクリプト**: `source_collector.py`

各ペルソナの公開ソース URL を `longlist.yaml` から読み取り、自動収集:
- 書籍: Open Library / Amazon API（メタ + 抜粋）
- インタビュー: YouTube transcript API + Web Article scraping
- SEC filings: EDGAR API (13F, 13D, 13G)
- SNS: X 公開アカウント (オプトイン公開のみ)

出力: `sources/{id}_{name}/` ディレクトリに JSON でメタ + raw text

### Phase 3: テキスト抽出 + 要約 (5/21-5/23)

**スクリプト**: `text_extractor.py`

ノイズ除去 + Claude API で意思決定パターン要約:
```python
prompt = f"""
以下は {investor_name} の公開発言・書籍・インタビュー抜粋です。
意思決定パターンを抽出してください:
1. リスク評価のしかた
2. エントリー判断の典型
3. エグジット判断の典型
4. 損切り・利確の閾値
5. ポジションサイズの決め方
6. 感情コントロールの言及
出力形式: YAML, 各項目に「典型的引用」を添付
"""
```

### Phase 4: DD SDK 入力変換 (5/23-5/24)

**スクリプト**: `persona_formatter.py`

DD SDK の入力フォーマット（要 `/home/sol/digital-double/` ドキュメント参照）に整形:
- OCEAN推定スコア
- 意思決定スタイル分類
- 引用ベース行動パターン

### Phase 5: DD SDK で人格モデル構築 (5/24-5/26)

**スクリプト**: `build_personas.py`

```python
from digital_double import DDBuilder

for investor in lookup_table:
    persona = DDBuilder.build(
        input_data=investor['extracted'],
        archetype_hint=investor['archetype'],
        context='institutional_investor',
    )
    save(persona, f'personas/{investor["id"]}_persona.json')
```

100体を並列実行（asyncio）。GTX1080TiでもCPUベースなら4並列で約2日。
H200があれば数時間で完了。

### Phase 6: 投資判断シミュレーション (5/26-5/29)

**スクリプト**: `run_simulation.py`

過去20年の市場イベント30件 × 100ペルソナ = 3,000意思決定:
- 各イベントで「この時、あなたなら何をしましたか」を生成
- 結果を `simulation_results/{id}.json` に保存
- 一致率測定 (個人投資家2,245体との比較も)

### Phase 7: 集計・分析・記事化 (5/30-6/2)

**スクリプト**: `analyze_results.py`

集計項目:
- 機関投資家 vs 個人投資家の意思決定差（タイプ分布、決定速度、確信度）
- 機関投資家内の Hit Rate 比較
- 「ペルソナ化できる/できない」境界線の検証
- バフェット型/ソロス型のどちらが現代市場で予測精度が高いか
- 仮説検証: 機関投資家は Noise Trader 比率が低いか?

→ 結果を番外編 #2 の記事素材として `article_data/wall7_part2.json` 出力

---

## 4. 著名人物リスト案（Phase 1 草稿）

詳細は `longlist.yaml` 完成版を参照。サンプル:

### Value (15名)
- Warren Buffett, Charlie Munger, Benjamin Graham, Peter Lynch, Walter Schloss
- Seth Klarman, Joel Greenblatt, Mohnish Pabrai, Bill Ackman, Howard Marks
- Tom Russo, François Rochon, Mason Hawkins, Glenn Greenberg, Christopher Browne

### Macro (15名)
- George Soros, Ray Dalio, Stanley Druckenmiller, Paul Tudor Jones, Bridgewater
- Louis Bacon, Andrew Hall, Michael Steinhardt, Julian Robertson
- Larry Summers (政策視点), 等

### Quants (10名)
- Jim Simons (Renaissance), David E. Shaw, Cliff Asness (AQR), Robert Mercer
- John Overdeck/David Siegel (Two Sigma), Edward Thorp, Igor Tulchinsky (WorldQuant)

### Growth/Tech (10名)
- Cathie Wood (ARK), Peter Thiel, Reid Hoffman, Marc Andreessen (a16z)
- Bill Gurley, Vinod Khosla, John Doerr, 等

### Activist (8名)
- Carl Icahn, Bill Ackman, Daniel Loeb, Nelson Peltz, Paul Singer

### Hedge Fund Veterans (12名)
- David Tepper, Steven Cohen, Ken Griffin, Israel Englander
- Jeffrey Gundlach, Bill Gross, Paul Marshall, 等

### Distressed (8名)
- Seth Klarman, David Tepper (再掲なし、別ヘッジ), Marc Lasry, Howard Marks

### 日本人 (10名)
- 村上世彰, 是川銀蔵, BNF, テスタ, cis
- 山口揚平, 藤野英人, 渋澤健, 武者陵司, 朝倉智也

### Crypto (5名)
- Michael Saylor, Cathie Wood (再掲なし), Mike Novogratz
- Naval Ravikant, Tim Draper

### Academic (7名)
- Fischer Black, Myron Scholes, Robert Merton, Eugene Fama
- Robert Shiller, Daniel Kahneman, Richard Thaler

→ Phase 1 完了後、最終100名で確定。

---

## 5. 完成スケジュール

| 週 | フェーズ | 主成果物 |
|---|--------|--------|
| W1 (5/17-5/24) | Phase 1-4 | longlist + sources + extracted + persona_inputs |
| W2 (5/24-5/31) | Phase 5-6 | personas + simulation_results |
| W3 (6/1-6/4) | Phase 7 + 記事化 | article_data + 記事完成 + note公開 |

---

## 6. リスクと対策

| リスク | 対策 |
|------|----|
| データ収集が長引く | Phase 2 は API + Web scraping で並列化、人手介入は最小限 |
| Claude API コスト | 要約は flash-lite 優先、深い分析のみ Claude Sonnet |
| ペルソナ品質不安定 | 構築後に「典型引用と一致するか」を Claude で自動検証 |
| 倫理的グレーゾーン | 故人・現役で迷う人物は事前にユーザーに相談 |
| 6/4 公開に間に合わない | Phase 5-6 は H200 クラスタで並列実行が前提 |

---

## 7. 必要なツール・環境

### 既存利用
- `/home/sol/digital-double/` (DD SDK)
- `/home/sol/persona-api/` (Persona API)
- H200×104 ワークステーション群（Phase 5-6 並列化用）

### 新規追加
- EDGAR API key (SEC公開資料アクセス)
- YouTube Data API key (transcript取得)
- Open Library API (公開図書メタ)

### Claude API 利用量
- Phase 3: 100名 × 平均1万トークン入力 × 2,000トークン出力 ≈ $50
- Phase 7: 集計分析 ≈ $30
- 合計: 約 $100

---

## 8. 関連ファイル

```
/home/sol/aiquant-lab/ventures/persona100/
├── PIPELINE_DESIGN.md          # 本ファイル
├── longlist.yaml               # Phase 1 成果物
├── source_collector.py         # Phase 2 (未実装)
├── text_extractor.py           # Phase 3 (未実装)
├── persona_formatter.py        # Phase 4 (未実装)
├── build_personas.py           # Phase 5 (未実装)
├── run_simulation.py           # Phase 6 (未実装)
├── analyze_results.py          # Phase 7 (未実装)
├── sources/                    # Phase 2 出力
├── extracted/                  # Phase 3 出力
├── persona_inputs/             # Phase 4 出力
├── personas/                   # Phase 5 出力
├── simulation_results/         # Phase 6 出力
└── article_data/               # Phase 7 出力
```

---

## 9. 着手時のチェックリスト

- [ ] Phase 1 (longlist.yaml) 完成 → ユーザー承認
- [ ] EDGAR API キー取得
- [ ] YouTube API キー取得
- [ ] H200 クラスタの空きリソース確認
- [ ] Claude API 予算承認（約 $100）
- [ ] Phase 2-7 のスクリプト実装着手
