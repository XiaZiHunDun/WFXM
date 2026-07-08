#!/usr/bin/env bash
# Dev assistant 10-task WeChat handler sim (灵文1号).
#
# Usage:
#   bash scripts/butler-wechat-dev-assistant-sim.sh           # 10 项全跑（慢，需 LLM）
#   bash scripts/butler-wechat-dev-assistant-sim.sh --quick   # DEV-01/02/06/07/09
#   bash scripts/butler-wechat-dev-assistant-sim.sh --list
#
# Skip: BUTLER_WECHAT_DEV_ASSISTANT_SIM=0
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export BUTLER_ENABLE_TERMINAL="${BUTLER_ENABLE_TERMINAL:-1}"
export BUTLER_TERMINAL_PROFILE="${BUTLER_TERMINAL_PROFILE:-dev}"
export BUTLER_TERMINAL_ALLOWLIST_EXTRA="${BUTLER_TERMINAL_ALLOWLIST_EXTRA:-python,python3}"
exec bash "$ROOT/scripts/butler-wechat-owner-sim.sh" \
  --manifest wechat-dev-assistant-10-scenarios.yaml "$@"
