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

# P2-F expansion (2026-06-30): full contracts + P0/P1-C core seams + ops/gateway adapters.
MODULES=(
  butler/contracts/__init__.py
  butler/contracts/bridge_access.py
  butler/contracts/compaction_ports.py
  butler/contracts/context_transform_ports.py
  butler/contracts/dev_context_ports.py
  butler/contracts/dev_state_ports.py
  butler/contracts/eval_ports.py
  butler/contracts/events.py
  butler/contracts/gateway_registry.py
  butler/contracts/hook_context_ports.py
  butler/contracts/memory_ports.py
  butler/contracts/message_ports.py
  butler/contracts/owner_gate.py
  butler/contracts/review_ports.py
  butler/contracts/sink_registry.py
  butler/tools/delegate_run_state.py
  butler/tools/delegate_record.py
  butler/core/approval_cards.py
  butler/core/events_sink.py
  butler/core/schema_recovery.py
  butler/core/llm_retry_errors.py
  butler/core/llm_retry_outcomes.py
  butler/core/tool_batch_finalize.py
  butler/ops/lazy_import_budget.py
  butler/ops/degradation_registry.py
  butler/tools/terminal_approval.py
  butler/dag_scheduler.py
  butler/gateway/network_route_verify_runner.py
  butler/gateway/events_sink_impl.py
  butler/workflow_step_runner.py
  butler/gateway/locked_phase_registry.py
  butler/defaults/model_defaults.py
  butler/orchestrator/templates.py
  butler/orchestrator/loop_factory.py
  butler/orchestrator/memory_bridge.py
  butler/orchestrator/skill_bridge.py
  butler/orchestrator/prompt_assembler.py
)

echo "== Butler mypy strict gate (${#MODULES[@]} modules) =="
for mod in "${MODULES[@]}"; do
  echo "  -> $mod"
  python -m mypy "$mod" --follow-imports=skip
done
echo "Mypy strict gate: OK"
