#!/usr/bin/env bash
# Warn when builtin tool descriptions overlap within the same toolset.
#   --warn-only   print issues but exit 0 (pre-release smoke)
set -euo pipefail

WARN_ONLY=0
if [[ "${1:-}" == "--warn-only" ]]; then
  WARN_ONLY=1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."

PY="${PYTHONPATH:+}${PYTHONPATH:+.}python3"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

WARN_ONLY="$WARN_ONLY" "$PY" - <<'PY'
import os
import sys

from butler.tools.orthogonality_lint import format_orthogonality_report, lint_builtin_tool_orthogonality

issues = lint_builtin_tool_orthogonality()
print(format_orthogonality_report(issues))
skipped = bool(issues and issues[0].startswith("orthogonality lint skipped"))
warn_only = os.environ.get("WARN_ONLY", "0") == "1"
if issues and not skipped:
    if warn_only:
        print(f"orthogonality lint: {len(issues)} warning(s) (warn-only, non-blocking)")
        sys.exit(0)
    sys.exit(1)
PY
