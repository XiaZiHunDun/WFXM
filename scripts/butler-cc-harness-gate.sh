#!/usr/bin/env bash
# CC harness regression gate (P0–P4): context economics, edit safety, queue, streaming.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

PY="${BUTLER_PYTHON:-python3}"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

echo "== CC harness P0–P2 (spill / prune / read-state / transition / queue / streaming) =="
"$PY" -m pytest \
  tests/test_tool_result_storage.py \
  tests/test_tool_prune_policy.py \
  tests/dev_engine/test_read_state.py \
  tests/test_loop_transition.py \
  tests/gateway/test_message_queue.py \
  tests/gateway/test_gateway_queue_drain_push.py \
  tests/test_streaming_tools.py \
  tests/test_cache_safe_delegate.py \
  -q "$@"

echo ""
echo "== CC harness P3–P4 + context pipeline =="
"$PY" -m pytest \
  tests/test_cc_p3_p4_features.py \
  tests/test_context_pipeline.py \
  tests/test_turn_compaction.py \
  tests/test_post_compact_agents_sections.py \
  tests/core/test_compaction_context_adapter.py \
  tests/core/test_context_pipeline_acl.py \
  tests/core/test_hook_context_adapter.py \
  tests/core/test_dev_context_adapter.py \
  tests/core/test_pre_compact_hook_acl.py \
  tests/core/test_compaction_checkpoint_acl.py \
  -q "$@"

echo ""
echo "== schema drift (compaction ACL contract, strict) =="
SCHEMA_DRIFT_STRICT=1 bash scripts/check-schema-drift.sh

echo ""
echo "== context compaction smoke subset =="
bash scripts/butler-context-compaction-smoke.sh

echo ""
echo "CC harness gate: OK"
