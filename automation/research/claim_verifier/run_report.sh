#!/bin/bash
# 週次レポート生成
set -euo pipefail
cd /home/sol/aiquant-lab
export PATH="/home/sol/.local/bin:/home/sol/.claude/local:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/sol"
exec /home/sol/.local/bin/uv run python automation/research/claim_verifier/weekly_report.py "$@"
