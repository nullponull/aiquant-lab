# Claim Forward Verifier

「AI 投資勝った系」の主張を**前向きに検証**するパイプライン。
バックテストの cherry-pick 問題を排除し、リアルタイムで的中率を測定する。

## SKU 6 (¥14,800) の根幹データ

連載と Brain B戦略の中で、以下の SKU の核心:

> **SKU 6: AI 投資主張のリアルタイム精度ダッシュボード**
> - 過去 6 ヶ月分の検証データ閲覧権
> - 月次レポートのアップデート
> - ¥14,800

## アーキテクチャ

```
[research-collector.timer] 毎日 23:00
        ↓ filtered.json (score>=6 アイテム)
        ↓
[claim-process.timer] 毎日 23:30
        ↓ Claude CLI で主張抽出
        ↓ asset/direction/horizon/target を構造化
        ↓ T=0 価格スナップショット (yfinance)
        ↓ SQLite に登録
        ↓ expires_at = now + horizon_hours
        ↓
[claim-verify.timer] 1 時間ごと
        ↓ expires_at <= now の claim を取得
        ↓ T=horizon 価格を再取得
        ↓ 仮想 ¥10,000 投資の P/L 計算
        ↓ WIN/LOSS/NEUTRAL 判定
        ↓ verifications テーブルに記録
        ↓
[claim-report.timer] 毎週月曜 06:00
        ↓ 過去 7 日分の集計
        ↓ data/claims/reports/weekly_YYYY-MM-DD.md
```

## 価値の独自性

| 既存の AI 投資検証 | このシステム |
|----------------|-----------|
| 過去データ後追いバックテスト | **前向き forward test** |
| Look-back bias 入る | **バイアス排除** |
| Cherry-pick 可能 | **T=0 で固定、後で動かせない** |
| 「過去 10 年勝てた」 | **「実際の主張がどうなったか」** |

## ファイル構成

```
claim_verifier/
├── README.md                    # 本ファイル
├── db.py                        # SQLite (claims, verifications)
├── claim_extractor.py           # LLM で主張を構造化抽出
├── snapshot.py                  # yfinance で T=0/T=horizon 価格取得
├── verifier.py                  # 期限切れ claim を検証
├── process_inbox.py             # research_inbox → 抽出 → DB 登録
├── weekly_report.py             # 週次レポート生成
├── run_*.sh                     # systemd 用ラッパー
└── claim-*.{service,timer}      # systemd ユニット
```

## DB スキーマ

```sql
claims (
    id, detected_at, source_item_url, source_name, source_author,
    raw_text, asset, asset_class, direction, horizon_hours,
    target_pct, target_price, conviction_score,
    entry_snapshot_price, entry_snapshot_at, entry_currency,
    expires_at, extracted_meta
)

verifications (
    id, claim_id, verified_at, exit_price,
    raw_return_pct, directional_return_pct,
    hypothetical_jpy_pl, outcome, target_hit, notes
)
```

## サポート資産

- **crypto**: BTC, ETH, SOL, XRP, DOGE, BNB, ADA, MATIC, AVAX (yfinance -USD ペア)
- **us_stock**: SPY, QQQ, AAPL, MSFT, NVDA, TSLA など (yfinance)
- **jp_stock**: 7203 → 7203.T (yfinance)
- **fx**: USDJPY=X, EURUSD=X など

## 主張抽出のルール

LLM (Claude Haiku) は以下を含む主張のみを抽出:
- 銘柄/資産が明示
- 方向 (LONG/SHORT/NEUTRAL) が読める
- 期間 (時間単位) が読める

抽出されない (=スキップ) 例:
- 「いつか必ず上がる」(期間なし)
- 「投資家心理は重要」(抽象的)
- 「昨日 50% 取れた」(過去自慢、未来主張なし)

## 運用コマンド

```bash
# 手動 process (今日の inbox を処理)
uv run python automation/research/claim_verifier/process_inbox.py

# 全期間 process
uv run python automation/research/claim_verifier/process_inbox.py --all

# 検証 (期限切れの claim だけ)
uv run python automation/research/claim_verifier/verifier.py

# 週次レポート
uv run python automation/research/claim_verifier/weekly_report.py --days 7

# 全 timer 状態
systemctl --user list-timers claim-*

# ログ
journalctl --user -u claim-process -n 50
journalctl --user -u claim-verify -n 50

# DB 内容確認
sqlite3 /home/sol/aiquant-lab/data/claims/claims.db "SELECT * FROM claims LIMIT 10;"
```

## レポート出力先

- 週次レポート: `/home/sol/aiquant-lab/data/claims/reports/weekly_YYYY-MM-DD.md`
- DB: `/home/sol/aiquant-lab/data/claims/claims.db`

## SKU 6 への展開

100 件以上の検証データが溜まったら:

1. 月次サンプル数を確認 (50+ で統計的に意味あり)
2. 統計検定で「ランダムより有意に優れているソース」「劣るソース」を特定
3. リアルタイムダッシュボード (Streamlit) を立ち上げ
4. 過去 6 ヶ月分のデータを SKU 6 として ¥14,800 で販売
5. 半年ごとにアップデート

## 法的配慮

- 個別主張の発信者は**完全匿名化** (DB 上は URL のみ、公開時はソース名のみ)
- 「特定発信者を批判する意図はない」を明記
- 検証は「学習素材として匿名化のうえ統計分析」

## コスト見積もり

- 主張抽出 LLM: ~10件/日 × $0.001 = $0.01/日
- 月次: $0.30 程度
- 価格取得: yfinance 無料

## 連載との関係

- 連載の核心テーゼ「AI で市場予測は壁にぶつかる」を**統計的に裏付ける**仕組み
- 検証データが蓄積するほど連載の主張が強化される
- Episode 6/9 の素材として直接使える
