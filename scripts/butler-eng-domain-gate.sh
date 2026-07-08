#!/usr/bin/env bash
# ENG-9 domain gate: gateway + memory + tools pytest subsets (~2–4 min).
# Usage: bash scripts/butler-eng-domain-gate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

echo "== Butler ENG domain gate =="
bash scripts/p3j-env-hygiene-gate.sh
bash scripts/p3i-lazy-import-report.sh
bash scripts/butler-domain-pytest.sh gateway memory tools
PYTHON_BIN="$(command -v python || command -v python3)"
"${PYTHON_BIN}" -m pytest \
  tests/test_locked_phase_registry.py \
  tests/test_model_defaults_literals.py \
  tests/test_eng7_approval_layering.py \
  tests/test_eng15_layer_dependency_matrix.py \
  tests/test_contracts_gateway_access.py \
  tests/test_lazy_import_budget.py \
  tests/test_owner_pmf_report.py \
  tests/test_env_parse_r8.py \
  tests/test_tool_boundary_validators.py \
  tests/gateway/test_rag_failure_degradation.py \
  tests/test_structured_events.py \
  tests/test_loop_transition_coverage.py \
  tests/test_query_relaxation.py \
  -q --tb=line
echo "ENG domain gate: OK"
