#!/usr/bin/env bash
# P3-J: env documentation hygiene (reference ↔ .env.example ↔ butler/ readers).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== P3-J env hygiene gate =="
bash scripts/check-env-reference-sync.sh
bash scripts/check-dead-env.sh
echo ""
echo "-- P3-J env audit (report) --"
bash scripts/p3j-env-audit.sh
echo ""
echo "-- P3-J env audit (strict) --"
P3J_AUDIT_STRICT=1 bash scripts/p3j-env-audit.sh
echo ""
echo "-- P3-J env schema PoC --"
python3 scripts/p3j-env-schema-poc.py
echo "P3-J env hygiene gate: OK"
