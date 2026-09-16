# 記憶から移設したノート

出所: `~/.claude` の記憶(2026-09-16)。記憶側は入口とポインタだけを持つ。

<!-- memory/ai-compass/project_aiquant_wall_series.md -->

## project_aiquant_wall_series

# 連載「AIで投資の壁を越える」プロジェクトメモリ

> **⚠️ 更新 (2026-07-11 実査)**: **claim-verify 系 5 ユニットが空回り中**。原因はスクリプト消失ではなく **2026-06-10 のリポ3層再編 (commit 3ddf176) で `automation/` 配下が `ventures/patent_mine/`・`ventures/research_monitor/` へ移動したのに systemd の ExecStart が旧パスのまま** (claim-process/claim-verify/patent-mine/patent-aggregate/research-collector が 203/EXEC)。5 つの .service のパス書き換えで直る。aiquant-publish.service は別原因 = note ログインセッション切れ。
> (旧記録 2026-07-04 実査: 稼働中、repo 最終コミット 2026-06-28)。ディレクトリ構造・戦略詳細は `/home/sol/aiquant-lab/` (README / POSTING_STRATEGY.md / articles/TITLE_TEMPLATE.md) と `/home/sol/brain-post-system/aiquant_products/` が正。

## 概要

2026年4月開始。AIコンパス (note https://note.com/ai_compass_media) 配下の連載 (毎週水曜12:00 note + X @nullpodesu 連動 + GitHub コード公開) で、「AIで市場予測は無理」と言われる境界線を6実験で検証する公開研究。**好奇心が先、収益は後**。プロジェクト: `/home/sol/aiquant-lab/` (Python 3.13 / uv / yfinance / Claude Haiku)。

## アカウント制約 (絶対)

- note は AIコンパス一本。**ぬるぽん以外の note アカウントはシャドウバン状態のため使わない**
- **「投資する体裁」は NG** = 完全な仮想シミュレーション徹底。投資助言と取れる断定・「絶対/必ず/保証」禁止。個人攻撃は匿名化
- ブランドトーン: 冷静 70% + 探求心 20% + ユーモア 10%。「データはこうなりました」で語る

## 6つの壁

再帰性(#4) / 非定常性(#1,#2) / グッドハート(#3,#6) / 複雑系(#7) / ファットテール(#5) / 自己言及性(#2)

## 第1回の核心結果 (実データ)

「3週間で4%勝った」AI自動売買戦略を10年バックテスト → 戦略 CAGR **13.29%** vs SPY バイアンドホールド **13.20%** (差 0.09% = 誤差レベル)。SPY だけで「3週間+4%」が起きる確率 13.2%。**凝った戦略も S&P500 放置とほぼ同じ、「3週間+4%」はノイズの範囲内**。

## 重要な学び

1. **Persona API は投資ペルソナを持たない** — 「行動アルファ」を堀に使うのは誤り
2. **ブランド統合の力** — 単独立ち上げより既存ブランド (AIコンパス) 配下が立ち上がり早い
3. **note エディタは markdown 表を自動レンダリングしない** → リスト変換必須 (Episode 0 で表が崩れた、変換コード適用済み)

## 実装済みインフラ

- **主張フォワード検証エンジン** `/home/sol/aiquant-lab/automation/research/claim_verifier/`: 主張系記事 → Claude CLI 構造化抽出 (asset/direction/horizon/target) → T=0 価格スナップショット → SQLite (`data/claims/claims.db`) → 期限切れ claim を1時間毎検証 → 週次レポート。systemd timer 3つ (claim-process/verify/report)。**前向き検証で cherry-pick 不能・look-back bias ゼロ** = SKU 6 の根幹データ。初回登録: Kronos ツイート (BTC LONG 72h +1400%、2026-04-30)
- **自動投稿** `automation/publish_episode.py` (aiquant-publish.timer 毎日12:00)。note = `note-post-mcp/publish-single.cjs` (Playwright 直接、MCP は subprocess 不可)、X = `x_poster.py` (**compose 直リンクは timeout する → home→SideNav 経由**)。state `~/.note-state-aicompass3.json`
- **日次リサーチコレクター** (research-collector.timer 23:00): RSS (Yahoo/東洋経済/日経) + note 検索 API + X 検索 → Claude haiku 分類 (sku5_scam/series_material/regime_change 等) → `data/research_inbox/`。高評価は brain-post-system 側にも自動保存。コスト月 $3-5
- 実験コード: `code/agents/` (solo / debate 10ペルソナ / evaluator = Generator/Evaluator 分離 / baseline)。**第2回は ANTHROPIC_API_KEY 設定 + `uv run python code/experiments/run_episode2.py --n-events 30` の実行待ちのまま**だった (Mock 動作確認済)
- WORLDmonitor (AGPL-3.0): 連載コンテンツ用途 OK、有料 SaaS 化は商用ライセンス要

## Brain B戦略 (収益化)

既存 Brain (A戦略) は売れず (5商材で1部)。B = **連載起点のエンジニア向け上位商材 5 SKU** (¥9,800〜29,800、仕様 `/home/sol/brain-post-system/aiquant_products/`、ローンチ 2026-05〜09 予定だった)。線引き: 連載 (無料) = 手法・結論・サマリー / Brain (有料) = コード一式・生データ・未公開失敗事例。専用文体ガイド `specs/00_writing_style.md` (友達LINE文体等の既存 Brain ルールは不適用、表OK・技術用語OK・AI臭定型禁止・失敗談必須)。

## 投稿実績 (このメモリに記録がある分)

Episode 0 マニフェスト: note n67ed9e6112a3 (2026-04-28 11:28) + X anchor https://x.com/nullpodesu/status/2048954850877346282 + 6返信。以降の実績は未記録 → 状態確認は note/aiquant-lab の実データで。
