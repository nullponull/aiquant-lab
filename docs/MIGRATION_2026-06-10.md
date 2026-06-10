# リポジトリ再編 移行ガイド (2026-06-10)

リポジトリを 3 層に再編しました。**本番サーバー (`/home/sol/aiquant-lab`) では
systemd ユニットの再インストールが必要です。**

## 新構成

| 旧 | 新 |
|---|---|
| `articles/`, `promo/`, `POSTING_STRATEGY.md`, `TODAY_LAUNCH_PLAN.md` | `media/` 配下 |
| `automation/publish_episode.py`, `x_poster.py`, `run.sh`, `state.json`, `*.service/timer` | `media/automation/` |
| `docs/` のメディア運用ドキュメント | `media/docs/` |
| `automation/research/` | `ventures/research_monitor/` |
| `automation/patent_mine/` | `ventures/patent_mine/` |
| `automation/persona100/` | `ventures/persona100/` |
| `data/claims/`, `data/research_inbox/` | `ventures/research_monitor/data/` 配下 |

研究コード (`code/`, `tests/`, `results/`, `data/cache/`) はルート直下のまま変更ありません。
コード内のパス参照 (PROJECT_ROOT、ExecStart、state.json 内の記事パス等) は更新済みです。

## サーバーでの移行手順

```bash
cd /home/sol/aiquant-lab
git pull

# 1. 旧ユニットを停止
sudo systemctl stop aiquant-publish.timer research-collector.timer \
  claim-process.timer claim-verify.timer claim-report.timer \
  patent-mine.timer patent-aggregate.timer patent-weekly.timer 2>/dev/null

# 2. 新しいパスのユニットファイルを再リンク/コピー
sudo cp media/automation/aiquant-publish.{service,timer} /etc/systemd/system/
sudo cp ventures/research_monitor/research-collector.* /etc/systemd/system/ 2>/dev/null
sudo cp ventures/research_monitor/claim_verifier/claim-*.{service,timer} /etc/systemd/system/
sudo cp ventures/patent_mine/patent-*.{service,timer} /etc/systemd/system/

# 3. リロードして再開
sudo systemctl daemon-reload
sudo systemctl start aiquant-publish.timer research-collector.timer \
  claim-process.timer claim-verify.timer claim-report.timer \
  patent-mine.timer patent-aggregate.timer patent-weekly.timer

# 4. 動作確認
systemctl list-timers | grep -E "aiquant|claim|patent|research"
```

## 確認ポイント

- `media/automation/state.json` の記事パスは `media/articles/...` に更新済み
- claim_verifier の SQLite は `ventures/research_monitor/data/claims/claims.db` を参照
  (旧 `data/claims/claims.db` は git mv 済みなので pull 後そのまま動く)
- 次回配信前に dry-run 推奨:
  `uv run python media/automation/publish_episode.py --dry-run`
