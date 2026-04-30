#!/bin/bash
# 候補集約 (毎日 patent-mine の後に実行)
set -euo pipefail
cd /home/sol/aiquant-lab
export PATH="/home/sol/.local/bin:/home/sol/.claude/local:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/sol"
exec /home/sol/.local/bin/uv run python automation/patent_mine/aggregate_candidates.py
