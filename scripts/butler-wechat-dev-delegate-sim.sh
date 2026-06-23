#!/usr/bin/env bash
# Multi-project dev delegate scenario sim (manifest-driven handler tests).
#
# Usage:
#   bash scripts/butler-wechat-dev-delegate-sim.sh                 # all tracks
#   bash scripts/butler-wechat-dev-delegate-sim.sh --quick         # skip slow / skip_in_quick
#   bash scripts/butler-wechat-dev-delegate-sim.sh --track lingwen
#   bash scripts/butler-wechat-dev-delegate-sim.sh --list
#   bash scripts/butler-wechat-dev-delegate-sim.sh --json-out /tmp/dev-delegate-sim.json
#
# Skip (exit 0): BUTLER_WECHAT_DEV_DELEGATE_SIM=0 or no LLM key
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Sub-agent py_compile / verify needs terminal in handler sim (Lead forbid_tools still blocks Lead shell).
export BUTLER_ENABLE_TERMINAL="${BUTLER_ENABLE_TERMINAL:-1}"
export BUTLER_TERMINAL_PROFILE="${BUTLER_TERMINAL_PROFILE:-dev}"
export BUTLER_TERMINAL_ALLOWLIST_EXTRA="${BUTLER_TERMINAL_ALLOWLIST_EXTRA:-python,python3}"
exec bash "$ROOT/scripts/butler-wechat-owner-sim.sh" \
  --manifest wechat-dev-delegate-scenarios.yaml "$@"
