#!/usr/bin/env bash
# Tiered smoke runner. Pre-release gate remains butler-pre-release-smoke.sh (--tier=full).
# Usage:
#   bash scripts/butler-smoke.sh              # default: standard
#   bash scripts/butler-smoke.sh --tier=quick
#   bash scripts/butler-smoke.sh --tier=standard
#   bash scripts/butler-smoke.sh --tier=full
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TIER="${BUTLER_SMOKE_TIER:-standard}"

for arg in "$@"; do
  case "$arg" in
    --tier=*) TIER="${arg#--tier=}" ;;
    --tier)
      shift
      TIER="${1:-standard}"
      ;;
    -h|--help)
      echo "Usage: $0 [--tier=quick|standard|full]"
      echo "  quick    gateway preflight + owner/gateway/wechat-attach pytest subset"
      echo "  standard quick + wechat smokes + lingwen lead + DemoPilot preflight"
      echo "  full     butler-pre-release-smoke.sh (9 steps)"
      exit 0
      ;;
  esac
done

# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
if [[ -f .env ]]; then
  butler_source_env "$ROOT/.env"
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

case "$TIER" in
  quick)
    echo "== butler-smoke tier=quick =="
    bash scripts/butler-gateway-ops.sh preflight
    echo ""
    python3 -m pytest -q --tb=line \
      tests/test_project_preflight.py \
      tests/test_project_lead.py \
      tests/gateway/test_gateway_handler.py \
      tests/gateway/test_wechat_attach_detail.py \
      tests/test_owner_gate.py \
      tests/test_owner_surface.py \
      tests/test_wechat_text_export.py \
      tests/test_cc_bridge.py \
      tests/test_sandbox_commands.py \
      tests/test_butler_v4.py
    echo ""
    echo "Smoke quick: ALL PASSED"
    ;;
  standard)
    echo "== butler-smoke tier=standard (quick + domain smokes) =="
    bash scripts/butler-gateway-ops.sh preflight
    echo ""
    python3 -m pytest -q --tb=line \
      tests/test_project_preflight.py \
      tests/test_project_lead.py \
      tests/gateway/test_gateway_handler.py \
      tests/test_owner_gate.py \
      tests/test_butler_v4.py
    echo ""
    bash scripts/butler-wechat-memory-smoke.sh
    bash scripts/butler-wechat-gateway-smoke.sh
    bash scripts/butler-inbound-media-smoke.sh
    bash scripts/butler-lingwen-lead-smoke.sh
    butler project preflight --project "普通试点项目"
    echo ""
    echo "Smoke standard: ALL PASSED"
    ;;
  full)
    exec bash scripts/butler-pre-release-smoke.sh
    ;;
  *)
    echo "Unknown tier: $TIER (use quick|standard|full)" >&2
    exit 2
    ;;
esac
