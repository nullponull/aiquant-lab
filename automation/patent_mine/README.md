# Patent Mine — 期限切れ特許の事業化候補発掘パイプライン

> note_ai_mousigo の手法をベースに、企業事業として実装可能性を
> 検証する仕組み。Phase 0 (技術検証) は既に動作。

---

## 何をするか

```
J-PlatPat / Google Patents で期限切れ特許検索
        ↓
Claude で 6 軸スコアリング
  - simplicity: 構造のシンプルさ
  - originality: 既存品との差別化
  - demand: 市場需要
  - cost_feasibility: 製造コスト適性
  - legal_clearance: 権利クリア容易さ
  - moq_compatibility: 小ロット適性
        ↓
viable / marginal / skip に分類
        ↓
shortlist 生成 → 弁理士確認 → 試作 → 量産 → 販売
```

---

## Phase 0 動作確認結果 (2026-04-30)

サンプル特許 10 件で動作:

| 項目 | 値 |
|------|-----|
| 投入件数 | 10 |
| viable | 7 件 |
| marginal | 2 件 |
| skip | 1 件 (高度な高効率太陽電池) |
| Top 候補 | ペット用自動給水ボウル (49/60, 粗利 73%) |

`results/scored_2026-04-30.json` と `results/shortlist_2026-04-30.md` 参照。

---

## 構成

```
patent_mine/
├── README.md                      # 本ファイル
├── PHASE1_LEGAL_CLEARANCE.md     # Phase 1 弁理士確認の手順
├── sources/
│   └── google_patents.py         # Google Patents 検索 (要 Playwright)
├── scorer.py                      # Claude 6 軸スコアリング ★ 動作確認済
├── run_pilot.py                   # Phase 0 パイロット ★ 動作確認済
├── data/
│   └── sample_patents.json       # サンプル 10 件 (動作確認用)
└── results/
    ├── scored_YYYY-MM-DD.json    # スコアリング結果
    └── shortlist_YYYY-MM-DD.md   # ショートリスト
```

---

## フェーズ別の状況

### Phase 0: 技術検証 ✅ 完了

- [x] Claude スコアラー実装・動作確認
- [x] Pipeline ランナー実装
- [x] サンプル 10 件で shortlist 生成
- [x] viable / marginal / skip 自動分類

### Phase 1: 法的クリア確認 (次のステップ)

- [ ] 実データソース選定 (3 つの選択肢)
- [ ] J-PlatPat / Google Patents で 100-1000 件検索
- [ ] スコアリング → viable 5-10 件抽出
- [ ] 弁理士に調査依頼
- [ ] CLEAR 判定 3-5 件確保

詳細: `PHASE1_LEGAL_CLEARANCE.md`

### Phase 2: 試作

- [ ] CLEAR 候補 1-2 件選定
- [ ] 3D プリント or 試作業者で物理サンプル
- [ ] Alibaba 見積もり取得

### Phase 3: 量産

- [ ] 国内/海外 OEM 業者選定
- [ ] 小ロット (100-500 個) 発注
- [ ] 品質確認

### Phase 4: 販売

- [ ] Amazon / Pinkoi / Creema 出品
- [ ] テスト販売 (3 ヶ月)
- [ ] 利益・損失データの記録

---

## 実データソース (Phase 1 で選定)

### 選択肢 A: J-PlatPat の Playwright UI 操作

- ✅ 完全無料
- ✅ 認証不要
- ✅ 日本特許に特化、経過情報が完全
- ❌ SPA で実装複雑、1 件取得に 30 秒〜
- ❌ 大量取得は CAPTCHA 注意

### 選択肢 B: EPO Espacenet OPS API

- ✅ 公式 API、安定的
- ✅ 月 4GB 無料枠
- ❌ API キー登録必要 (https://ops.epo.org/3.2/)
- ❌ 日本特許の経過情報は J-PlatPat が必要 (補完的役割)

### 選択肢 C: Lens.org Patent API

- ✅ 公式 API
- ✅ 一部無料
- ❌ API キー登録必要
- ❌ 日本特許の細部は弱い

**推奨**: A (J-PlatPat Playwright) を主用、B (EPO) を補完

---

## 投資見積もり (企業事業として)

| Phase | 期間 | 投資 | 期待返り |
|------|------|------|--------|
| Phase 0 (本完了) | 1 日 | ¥0 (Mock) | Pipeline 動作確認 |
| Phase 1 | 2-3 週 | ¥75-450K (弁理士) | CLEAR 候補 3-5 件 |
| Phase 2 | 1-2 ヶ月 | ¥30-100K (試作) | 物理サンプル |
| Phase 3 | 2-3 ヶ月 | ¥100-300K (小ロット) | 在庫 100-500 個 |
| Phase 4 | 3 ヶ月 | ¥30-100K (出品料・販促) | 実利益データ |
| **合計** | **6-12 ヶ月** | **¥235-950K** | **企業事業判断** |

---

## 期待される結果

楽観シナリオ:
- 1-2 件が継続販売 → 月商 ¥50-200K, 粗利 30-50%
- 連載・SKU の独占データになる

中シナリオ:
- 全候補が薄利 or 赤字
- 「やってみたが厳しい」というデータ自体が価値

悲観シナリオ:
- 全候補が法的問題発覚 / 量産失敗
- それでも Phase 1 までの記録は連載素材

**いずれの場合も** 連載「AIで投資の壁を越える」Episode 9 の素材として十分。

---

## 実行コマンド

```bash
# Phase 0 パイロット (サンプル 10 件)
cd /home/sol/aiquant-lab
uv run python automation/patent_mine/run_pilot.py

# 個別特許のスコアリング
uv run python automation/patent_mine/scorer.py
```

---

## 連載・SKU との関係

### 連載 Episode 9 候補

「**Claude で期限切れ特許から商品を発掘できるか — 6 ヶ月実証実験**」

連載第 9 回として:
- 全 4 フェーズの実装ログ
- 投資・回収・損失の全データ
- 失敗ポイントの解剖
- 「AI クオンツ的アプローチを物販に応用したらどうなるか」

### 将来の SKU 7 候補

「**Claude × 期限切れ特許の物販戦略実装ガイド**」 ¥19,800

実証データ + コード + 法的チェックリスト + 試作パートナー一覧
を商材化。

---

## 連動システム

- 既存の `claim_verifier` と異なるドメイン (株 vs 物販)
- 既存の `research_collector` とは独立
- ただし「実装で確かめる」精神は共通

---

## 法的免責

本パイプラインは事業化候補のスクリーニング支援ツールであり、
最終判断は弁理士・法律専門家による検証が必要です。
特許権侵害が発生した場合、開発者は責任を負いません。
