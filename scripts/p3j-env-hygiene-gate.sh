#!/usr/bin/env bash
# P3-J: env documentation hygiene (reference ↔ .env.example ↔ butler/ readers).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== P3-J env hygiene gate =="
bash scripts/check-env-reference-sync.sh
bash scripts/check-dead-env.sh
echo "P3-J env hygiene gate: OK"
