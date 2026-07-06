#!/usr/bin/env bash
# List main modules with 0 mypy errors not yet in strict gate.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
gate_files=$(rg -o 'butler/[^ ]+\.py' scripts/butler-mypy-strict-gate.sh | sort -u)
for dir in butler/core butler/gateway butler/runtime butler/tools butler/transport butler/mcp butler/memory butler/skills butler/session butler/hooks butler/eval butler/orchestrator butler/dev_engine butler/ops butler/registry butler/workflows butler/delegate butler/permissions butler/project; do
  [ -d "$dir" ] || continue
  for f in "$dir"/*.py; do
    [ -f "$f" ] || continue
    case "$f" in *_ops.py) continue ;; esac
    echo "$gate_files" | rg -qx "$f" && continue
    if python -m mypy "$f" --follow-imports=skip 2>/dev/null | rg -q 'error:'; then
      continue
    fi
    echo "$f"
  done
done
