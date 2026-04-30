#!/bin/bash
# 週次 top picks + ALERT 検出 (毎週月曜 06:00)
set -euo pipefail
cd /home/sol/aiquant-lab
export PATH="/home/sol/.local/bin:/home/sol/.claude/local:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/sol"
# 集約 → 週次レポート の順
/home/sol/.local/bin/uv run python automation/patent_mine/aggregate_candidates.py
exec /home/sol/.local/bin/uv run python automation/patent_mine/weekly_top_picks.py
