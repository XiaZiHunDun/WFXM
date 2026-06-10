#!/usr/bin/env bash
# C3: 演示试点 Lead 冒烟（第二 Lead 项目）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="演示试点"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== sync demo project skills =="
bash "$ROOT/scripts/sync-project-skills.sh" DemoPilot

echo ""
echo "== 1/3 preflight =="
butler project preflight --project "$PROJECT"

echo ""
echo "== 2/3 lead allowlist =="
python3 <<'PY'
from butler.project.lead import gateway_loop_role, is_lead_project
from butler.project.manager import get_project_manager
from butler.tools.project_tools import allowed_tool_names_for_project

pm = get_project_manager()
proj = pm.get_project("演示试点")
assert proj is not None
assert is_lead_project("演示试点", project=proj), "expected lead:true on 演示试点"
assert gateway_loop_role("演示试点", project=proj) == "lead"
allowed = allowed_tool_names_for_project(proj, role="lead")
assert allowed is not None
for name in ("read_file", "delegate_task", "run_workflow"):
    assert name in allowed
for forbidden in ("patch", "terminal", "write_file"):
    assert forbidden not in allowed
print("demo lead allowlist OK")
PY

echo ""
echo "== 3/3 lead skill on disk =="
test -f "projects/DemoPilot/skills/demo-project-lead.md"

echo ""
echo "Demo lead smoke: ALL PASSED"
