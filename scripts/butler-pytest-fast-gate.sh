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
bash scripts/butler-p0a-exception-gate.sh
echo ""
bash scripts/butler-p0b-degradation-gate.sh
echo ""
bash scripts/butler-p1c-gate.sh
echo ""
echo "== schema drift (all ACL contracts, strict) =="
SCHEMA_DRIFT_STRICT=1 bash scripts/check-schema-drift.sh
echo ""
echo "== P3-J env hygiene (fast gate) =="
bash scripts/p3j-env-hygiene-gate.sh
echo ""
echo "== G1: Lazy import budget (≤1910) =="
bash scripts/p3i-lazy-import-report.sh
echo ""
echo "== G2: Contract tests (Port + Shim __all__) =="
PYTHONPATH=. python3 -m pytest tests/contracts/ -q --tb=line
echo ""
echo "== G6: File size guard (>800 warn / >1200 block) =="
python3 scripts/ai_guard/file_size_check.py --ci
echo ""
bash scripts/butler-mypy-strict-gate.sh
echo ""
bash scripts/butler-trajectory-compliance-gate.sh --strict
echo ""
echo "Fast gate: ALL PASSED"
