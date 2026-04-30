#!/bin/bash
# 期限切れ主張を検証
set -euo pipefail
cd /home/sol/aiquant-lab
export PATH="/home/sol/.local/bin:/home/sol/.claude/local:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/sol"
exec /home/sol/.local/bin/uv run python automation/research/claim_verifier/verifier.py "$@"
