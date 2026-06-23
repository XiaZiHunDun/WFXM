#!/usr/bin/env bash
# Lead readonly scenario sim — forbid delegate_task on workflow/status queries.
#
# Usage:
#   bash scripts/butler-wechat-lead-readonly-sim.sh
#   bash scripts/butler-wechat-lead-readonly-sim.sh --quick
#
# Skip (exit 0): BUTLER_WECHAT_LEAD_READONLY_SIM=0 or no LLM key
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export BUTLER_WECHAT_OWNER_SIM="${BUTLER_WECHAT_LEAD_READONLY_SIM:-1}"
exec bash "$ROOT/scripts/butler-wechat-owner-sim.sh" \
  --manifest wechat-lead-readonly-scenarios.yaml "$@"
