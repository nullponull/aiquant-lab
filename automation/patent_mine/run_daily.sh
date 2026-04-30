#!/bin/bash
# patent_mine 日次自動実行 (ちょっとずつ運用)
# 毎日 1 キーワードを自動選択して実行
set -euo pipefail
cd /home/sol/aiquant-lab
export PATH="/home/sol/.local/bin:/home/sol/.claude/local:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/sol"
exec /home/sol/.local/bin/uv run python automation/patent_mine/run_jplatpat_daily.py --max-results 50
