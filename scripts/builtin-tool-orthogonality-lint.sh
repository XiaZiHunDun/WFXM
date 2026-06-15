#!/usr/bin/env bash
# Warn when builtin tool descriptions overlap within the same toolset.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."

PY="${PYTHONPATH:+}${PYTHONPATH:+.}python3"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

"$PY" - <<'PY'
from butler.tools.orthogonality_lint import format_orthogonality_report, lint_builtin_tool_orthogonality

issues = lint_builtin_tool_orthogonality()
print(format_orthogonality_report(issues))
if issues and not issues[0].startswith("orthogonality lint skipped"):
    raise SystemExit(1)
PY
