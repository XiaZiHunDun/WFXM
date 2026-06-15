#!/usr/bin/env bash
# Owner inbox / trust surface smoke (Phase 0–4 gateway commands, no API keys).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."

PY=python3
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

echo "== owner inbox / trust pytest (Phase 0–4) =="
"$PY" -m pytest \
  tests/test_session_continuity.py \
  tests/test_phase1_recall_compaction.py \
  tests/test_phase2_brief_narrative.py \
  tests/test_phase3_owner_quality.py \
  tests/test_phase4_owner_trust.py \
  -q --tb=line "$@"

echo ""
echo "== owner surface import smoke =="
"$PY" - <<'PY'
from butler.ops.butler_inbox import collect_inbox_snapshot, format_owner_brief
from butler.ops.owner_trust_surface import format_trust_report
from butler.core.memory_source_surface import format_memory_sources_report
from unittest.mock import MagicMock

orch = MagicMock()
health = {
    "memory_experience_hits": 2,
    "skill_injection_mode": "fallback",
    "memory_last_turn_sources": {"memory_experience_hits": 2},
}
brief = format_owner_brief(orch, "smoke:sk", health=health)
assert "管家简报" in brief
assert "信任" in brief or "MCP" in brief
trust = format_trust_report(orch, "smoke:sk", health=health)
assert "信任与透明度" in trust
mem = format_memory_sources_report(health)
assert "记忆" in mem
print("owner surface smoke: OK")
PY

echo ""
echo "Owner inbox smoke: PASSED"
echo "真机复测: /简报 /inbox /信任 /记忆来源（见 personal-butler-engineering-plan §真机补验）"
