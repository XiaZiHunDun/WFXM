#!/usr/bin/env bash
# 微信核心场景 pytest（BUTLER_SYNC_CONVERSATION_MEMORY=0 与生产一致）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."
export BUTLER_SYNC_CONVERSATION_MEMORY=0

echo "== wechat gateway core pytest (SYNC_CONVERSATION_MEMORY=0) =="
python3 -m pytest \
  tests/test_project_manager.py \
  tests/test_project_session_isolation.py \
  tests/test_project_tools_filter.py \
  tests/test_report_format.py \
  tests/test_tenant_isolation.py \
  tests/test_workflows.py \
  tests/test_wechat_session_reset.py \
  tests/test_gateway_acceptance.py \
  tests/test_wechat_ilink_inbound.py \
  tests/test_wechat_ilink_outbound.py \
  tests/test_wechat_ilink_media.py \
  tests/test_owner_profile_gateway.py \
  tests/test_wechat_account_persistence.py \
  tests/test_gateway_runner.py::TestButlerMessageHandlerRunner \
  tests/test_main_cli.py::TestWechatSetupCommand \
  tests/test_session_lifecycle.py \
  tests/test_post_session.py \
  tests/test_p0_memory_pilot.py \
  tests/test_memory_p1_p2.py \
  tests/test_memory_consistency.py \
  tests/test_memory_quality.py \
  tests/test_semantic_memory.py \
  tests/test_memory_reindex.py \
  tests/test_semantic_memory_p1.py \
  tests/test_memory_recall_fixtures.py \
  tests/test_memory_bullet_edit.py \
  tests/test_memory_m3_m4_smoke.py \
  -q --tb=line

echo "Wechat gateway smoke done."
