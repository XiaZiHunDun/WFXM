#!/usr/bin/env bash
# List main modules NOT in gate with mypy error counts (1-5 only).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
gate_files=$(rg -o 'butler/[^ ]+\.py' scripts/butler-mypy-strict-gate.sh | sort -u)
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
for dir in butler/core butler/gateway butler/runtime butler/tools butler/transport butler/mcp butler/memory butler/skills butler/session butler/hooks butler/eval butler/orchestrator butler/dev_engine butler/ops; do
  [ -d "$dir" ] || continue
  for f in "$dir"/*.py; do
    [ -f "$f" ] || continue
    case "$f" in *_ops.py) continue ;; esac
    echo "$gate_files" | rg -qx "$f" && continue
    out=$(python -m mypy "$f" --follow-imports=skip 2>&1 || true)
    cnt=$(echo "$out" | rg -c 'error:' || true)
    cnt=${cnt:-0}
    if [ "$cnt" -ge 1 ] && [ "$cnt" -le 5 ]; then
      echo "$cnt $f"
    fi
  done
done | sort -n
