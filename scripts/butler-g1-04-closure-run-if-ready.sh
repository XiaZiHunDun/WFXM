#!/usr/bin/env bash
# Run G1-04 closure apply when observation window is complete (exit 0 from check).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== G1-04 closure (if ready) =="
if ! bash "$ROOT/scripts/butler-g1-04-closure-check.sh"; then
  ec=$?
  echo "G1-04: not ready (exit $ec) — skip apply"
  exit 0
fi

echo ""
bash "$ROOT/scripts/butler-g1-04-closure-apply.sh"
echo ""
echo "Next: git diff && git commit -m 'docs: close G1-04 OT2 observation window' && git push"
