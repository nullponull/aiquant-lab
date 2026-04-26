# 自動投稿システム

連載「AIで投資の壁を越える」を note (AIコンパス) と X (ぬるぽん) に自動投稿する仕組み。

既存の以下のシステムを活用:
- **note 投稿**: `daily-note-post` の note_publisher 方式 (Claude CLI + MCP note-post)
- **X 投稿**: `xpost-community/scripts/x_playwright_poster.py` (Playwright cookie方式)

## 構成

```
automation/
├── publish_episode.py          # メインロジック
├── run.sh                      # systemd 用ラッパー
├── state.json                  # エピソード進捗管理
├── aiquant-publish.service     # systemd service
└── aiquant-publish.timer       # systemd timer (毎日 12:00)
```

## state.json の構造

各エピソードに以下のフィールド:
- `number`: エピソード番号 (0=マニフェスト, 1, 2, ...)
- `article_path`: note 投稿用 markdown のパス
- `x_promo_path`: X 連投スレッド用 promo ファイルのパス
- `scheduled_for`: 投稿予定日時 (ISO8601, JST)
- `published`: 投稿済みかどうか
- `note_url`: 投稿後の note URL (自動記録)
- `x_thread_id`: 投稿後の X スレッド最初のツイート ID
- `published_at`: 実際の投稿時刻

## 動作フロー

```
systemd timer (12:00 daily)
    ↓
run.sh
    ↓
publish_episode.py
    ↓
state.json から「scheduled_for ≤ 現在 かつ未公開」のエピソードを検索
    ↓
publish_to_note(article_path)  ← Claude CLI + MCP note-post
    ↓
parse_x_thread(promo_path)     ← X promo ファイルから連投スレッド抽出
    ↓
post_x_thread(tweets)          ← Playwright で連投 (5秒間隔)
    ↓
state.json 更新 (published=true, URL記録)
```

## 投稿スケジュール

state.json で管理。毎週水曜 12:00 を基本とする。

| 回 | 日時 | 種別 |
|---|------|------|
| #0 | 2026-04-27 月 12:00 | マニフェスト |
| #1 | 2026-04-29 水 12:00 | 検証 (10年バックテスト) |
| #2 | 2026-05-06 水 12:00 | 検証 (Claude CLI の壁) |

## 手動実行

```bash
# Dry-run (実投稿しない)
cd /home/sol/aiquant-lab
uv run python automation/publish_episode.py --dry-run --episode 0

# 特定エピソードを今すぐ強制投稿
uv run python automation/publish_episode.py --episode 0

# X だけ投稿しない (note のみ)
uv run python automation/publish_episode.py --episode 0 --no-x

# note だけ投稿しない (X のみ)
uv run python automation/publish_episode.py --episode 0 --no-note
```

## systemd timer の管理

```bash
# 状態確認
systemctl --user status aiquant-publish.timer
systemctl --user list-timers aiquant-publish.timer

# 一時停止
systemctl --user stop aiquant-publish.timer

# 完全無効化
systemctl --user disable aiquant-publish.timer

# 再有効化
systemctl --user enable aiquant-publish.timer
systemctl --user start aiquant-publish.timer

# ログ確認
journalctl --user -u aiquant-publish -n 50
journalctl --user -u aiquant-publish -f  # フォロー
```

## 新エピソード追加手順

1. `articles/` に記事 markdown を配置
2. `promo/` に X 連投スレッドの markdown を配置（既存 promo ファイルの形式に合わせる）
3. `state.json` の `episodes` 配列にエントリを追加:
```json
{
  "number": 3,
  "article_path": "articles/003_xxx.md",
  "x_promo_path": "promo/003_xxx_x.md",
  "scheduled_for": "2026-05-13T12:00:00+09:00",
  "type": "episode",
  "title": "...",
  "published": false,
  "note_url": null,
  "x_thread_id": null,
  "published_at": null
}
```
4. 次の timer 起動時に自動投稿される

## 依存

- Claude CLI (`claude` コマンド) - note 投稿時に MCP note-post ツールを呼び出す
- `~/.note-state.json` - note.com の認証クッキー
- `/home/sol/xpost-community/.x_cookies.json` - X の認証クッキー
- `/home/sol/xpost-community/scripts/x_playwright_poster.py` - X 投稿モジュール
- uv (Python 環境管理)

## トラブルシューティング

### note 投稿が失敗する

```bash
# 認証状態確認
ls -la ~/.note-state.json

# 認証更新が必要なら
cd /home/sol/daily-note-post
python3 refresh_note_auth.py
```

### X 投稿が失敗する

```bash
# クッキー確認
ls -la /home/sol/xpost-community/.x_cookies.json
# 8KB 以上、24時間以内であれば OK

# クッキー更新
cd /home/sol/xpost-community
python3 scripts/refresh_x_cookies.py
```

### 同じエピソードが二重投稿される

`state.json` の該当エピソードの `published: true` を確認。手動実行で強制再投稿した場合などは、state.json を直接編集して revert できる。

## ログファイル

systemd 経由の実行は journalctl に記録される。手動実行の標準出力をファイルに残したい場合:

```bash
uv run python automation/publish_episode.py 2>&1 | tee logs/publish-$(date +%Y%m%d_%H%M).log
```
