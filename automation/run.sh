#!/bin/bash
# 連載自動投稿ラッパー（systemd timer から呼ばれる）
set -euo pipefail

cd /home/sol/aiquant-lab

# 環境変数
export PATH="/home/sol/.local/bin:/home/sol/.claude/local:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/sol"

# uv 経由で実行（依存関係が解決される）
exec /home/sol/.local/bin/uv run python automation/publish_episode.py "$@"
