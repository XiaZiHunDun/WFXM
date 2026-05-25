#!/usr/bin/env bash
# Copy to projects/<slug>/.butler/harness/eval.sh — read-only harness entry.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# Replace with your fixed eval; must print a parseable metric line.
echo "METRIC score=1.0"
exit 0
