#!/usr/bin/env bash
# Report main modules with bare `except Exception` not yet in P0-A gate budgets.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== P0-A remaining scan =="
GATE_FILE="tests/test_p0a_exception_governance.py"
GATED=$(rg -o '"butler/[^"]+\.py"' "$GATE_FILE" | tr -d '"' | sort -u)

TMP=$(mktemp)
rg 'except Exception' butler --glob '*.py' \
  | rg -v '_ops\.py|best_effort\.py|review_static|review_knowledge' \
  | cut -d: -f1 | sort -u > "$TMP"

TOTAL=$(wc -l < "$TMP" | tr -d ' ')
MISSING=0
while IFS= read -r f; do
  if ! echo "$GATED" | rg -qx "$f"; then
    COUNT=$(rg -c '^\s*except\s+Exception\b' "$f" 2>/dev/null || echo 0)
    echo "  MISSING  $f  ($COUNT)"
    MISSING=$((MISSING + 1))
  fi
done < "$TMP"

echo "---"
echo "Main files with except Exception: $TOTAL"
echo "Not in gate budgets: $MISSING"
rm -f "$TMP"
