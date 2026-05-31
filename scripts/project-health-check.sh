#!/usr/bin/env bash
# Unified project hygiene check: code, config, docs, tests.
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH=.

MODE="${1:-quick}"
if [[ "${MODE}" != "quick" && "${MODE}" != "full" ]]; then
  echo "Usage: $0 [quick|full]"
  exit 2
fi

echo "== 1) Syntax compile check =="
python3 -m compileall -q butler

echo "== 1.5) Lint check (E/F) =="
python3 -m ruff check \
  butler/config_service.py \
  butler/tools/config_tools.py \
  butler/tools/web_search.py \
  butler/tools/multimodal_tools.py \
  butler/gateway/error_cards.py \
  --select E,F

echo "== 2) Key import smoke =="
python3 - <<'PY'
modules = [
    "butler.core.agent_loop",
    "butler.core.tool_batch",
    "butler.core.context_pipeline",
    "butler.core.llm_retry",
    "butler.gateway.message_handler",
    "butler.gateway.session_registry",
    "butler.gateway.command_registry",
    "butler.gateway.commands",
    "butler.project.lead",
    "butler.project.manager",
    "butler.project.preflight",
    "butler.tools.registry",
    "butler.tools.config_tools",
    "butler.tools.web_search",
    "butler.tools.multimodal_tools",
    "butler.config_service",
    "butler.memory.embedding",
    "butler.memory.vector_store",
    "butler.transport.llm_client",
    "butler.ops.health_report",
]
for m in modules:
    __import__(m)
print(f"imports ok: {len(modules)} modules")
PY

echo "== 3) Config docs alignment check =="
python3 - <<'PY'
from pathlib import Path

env = Path(".env.example").read_text(encoding="utf-8")
ref = Path("docs/config/reference.md").read_text(encoding="utf-8")
for key in (
    "BUTLER_ENABLE_WEB_SEARCH",
    "BUTLER_WEB_SEARCH_TIMEOUT",
    "BUTLER_DATA_QUERY",
    "BUTLER_POST_SESSION_LAYERED",
    "BUTLER_IMAGE_GENERATION",
    "BUTLER_TTS",
    "BUTLER_WECHAT_CONTENT_DEDUP_TTL",
    "BUTLER_WECHAT_MESSAGE_ID_DEDUP_TTL",
):
    if key not in env:
        raise SystemExit(f"missing in .env.example: {key}")
    if key not in ref:
        raise SystemExit(f"missing in docs/config/reference.md: {key}")
print("config docs alignment ok")
PY

echo "== 4) Core gate tests =="
pytest \
  tests/test_cc_p3_p4_features.py \
  tests/test_p2_remaining_features.py \
  tests/test_orchestration_improvements.py \
  tests/test_runtime_metrics.py \
  tests/test_tool_result_storage.py \
  tests/test_message_queue.py \
  tests/test_gateway_queue_command.py \
  tests/test_p2_workflow_permissions.py \
  tests/test_gateway_handler.py \
  -q -o "addopts="

echo "== 5) Product tools tests =="
pytest \
  tests/test_config_service.py \
  tests/test_web_search.py \
  tests/test_multimodal_tools.py \
  tests/test_p2_ux_features.py \
  tests/test_daily_life_gateway.py \
  tests/test_sprint_bcd.py \
  -q -o "addopts="

echo "== 6) Conversational suite collect check =="
pytest tests/conversational --collect-only -q -o "addopts=" >/dev/null
echo "conversational collect ok"

if [[ "${MODE}" == "full" ]]; then
  echo "== 7) Corpus tests (full mode) =="
  pytest tests/corpus -q -o "addopts="

  echo "== 8) Five-reports gate (full mode) =="
  bash scripts/butler-five-reports-gate.sh
fi

echo "project-health-check: OK (${MODE})"
