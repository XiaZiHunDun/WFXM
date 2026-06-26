#!/usr/bin/env bash
# PROD-P4 Owner UX gate (P4-A + P4-B).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

echo "=== PROD-P4 Owner UX gate ==="
python3 -m pytest tests/test_owner_ux_p4.py tests/test_owner_ux_p4b.py tests/test_owner_surface.py -q \
  --tb=short -k "help or diagnostic or acceptance or five_intents or tier1 or edit or handoff or cc_handoff"
echo "PROD-P4 GATE: PASS"
