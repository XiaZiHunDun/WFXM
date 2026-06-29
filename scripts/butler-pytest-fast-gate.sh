#!/usr/bin/env bash
# Local / PR fast gate: smoke quick + WeChat attach + CC harness (~3–5 min).
# Usage: bash scripts/butler-pytest-fast-gate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Butler pytest fast gate =="
bash scripts/butler-smoke.sh --tier=quick
echo ""
bash scripts/butler-wechat-attach-smoke.sh
echo ""
bash scripts/butler-wechat-attach-probe.sh
echo ""
bash scripts/butler-cc-harness-gate.sh
echo ""
bash scripts/butler-mypy-strict-gate.sh
echo ""
bash scripts/butler-trajectory-compliance-gate.sh --warn-only
echo ""
echo "Fast gate: ALL PASSED"
