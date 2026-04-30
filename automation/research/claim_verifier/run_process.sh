#!/bin/bash
# 主張抽出 → DB 登録 → T=0 スナップ
set -euo pipefail
cd /home/sol/aiquant-lab
export PATH="/home/sol/.local/bin:/home/sol/.claude/local:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/sol"
exec /home/sol/.local/bin/uv run python automation/research/claim_verifier/process_inbox.py "$@"
