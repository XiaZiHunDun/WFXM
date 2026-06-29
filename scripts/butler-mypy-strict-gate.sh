#!/usr/bin/env bash
# Mypy strict gate for opt-in modules (--follow-imports=skip keeps it fast).
# Usage: bash scripts/butler-mypy-strict-gate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python >/dev/null 2>&1; then
  echo "python not found" >&2
  exit 1
fi

python -c "import mypy" 2>/dev/null || {
  echo "mypy not installed (pip install -e '.[dev]')" >&2
  exit 1
}

MODULES=(
  butler/contracts/events.py
  butler/contracts/sink_registry.py
  butler/tools/delegate_run_state.py
  butler/core/approval_cards.py
  butler/tools/terminal_approval.py
  butler/dag_scheduler.py
  butler/gateway/network_route_verify_runner.py
  butler/workflow_step_runner.py
  butler/gateway/locked_phase_registry.py
  butler/defaults/model_defaults.py
)

echo "== Butler mypy strict gate (${#MODULES[@]} modules) =="
for mod in "${MODULES[@]}"; do
  echo "  -> $mod"
  python -m mypy "$mod" --follow-imports=skip
done
echo "Mypy strict gate: OK"
