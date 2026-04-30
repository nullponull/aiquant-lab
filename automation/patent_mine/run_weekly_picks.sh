#!/bin/bash
# 週次 top picks v2 (PDCA 統合) - 毎週月曜 06:00
# Top 5 候補に対して特許本文取得 + Amazon JP 競合調査 + Claude PDCA 判定
# GO 判定があったら ALERT/GO_ALERT_*.md 生成
set -euo pipefail
cd /home/sol/aiquant-lab
export PATH="/home/sol/.local/bin:/home/sol/.claude/local:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/sol"
# 集約 → PDCA + 週次レポート
/home/sol/.local/bin/uv run python automation/patent_mine/aggregate_candidates.py
exec /home/sol/.local/bin/uv run python automation/patent_mine/weekly_top_picks_v2.py
