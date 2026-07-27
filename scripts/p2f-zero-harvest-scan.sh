#!/usr/bin/env bash
# List main modules with 0 mypy errors not yet in strict gate (recursive).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
gate_files=$(rg -o 'butler/[^ ]+\.py' scripts/butler-mypy-strict-gate.sh | sort -u)
SCAN_DIRS=(
  butler/cli
  butler/eval_integration
  butler/defaults
  butler/report
  butler
  butler/io
  butler/experiments
  butler/core
  butler/gateway
  butler/runtime
  butler/tools
  butler/transport
  butler/mcp
  butler/memory
  butler/skills
  butler/session
  butler/hooks
  butler/eval
  butler/orchestrator
  butler/dev_engine
  butler/ops
  butler/registry
  butler/workflows
  butler/delegate
  butler/permissions
  butler/project
  butler/execpolicy
  butler/extensions
  butler/plan
  butler/prompt_eval
  butler/tests_policies
  butler/gateway/commands
  butler/gateway/platforms
  butler/transport/multimodal
)
for dir in "${SCAN_DIRS[@]}"; do
  [ -d "$dir" ] || continue
  while IFS= read -r -d '' f; do
    case "$f" in *_ops.py) continue ;; esac
    echo "$gate_files" | rg -qx "$f" && continue
    if python -m mypy "$f" --follow-imports=skip 2>/dev/null | rg -q 'error:'; then
      continue
    fi
    echo "$f"
  done < <(find "$dir" -name '*.py' ! -name '*_ops.py' -print0)
done
