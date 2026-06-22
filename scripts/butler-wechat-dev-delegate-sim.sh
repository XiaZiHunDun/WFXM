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
exec bash "$ROOT/scripts/butler-wechat-owner-sim.sh" \
  --manifest wechat-dev-delegate-scenarios.yaml "$@"
