#!/usr/bin/env bash
# 灵文1号 Lead 冒烟：preflight + 厂长工具白名单 + workflow_state 只读断言
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="灵文1号"
STATE_JSON="projects/LingWen1/novel-factory/workflow_state.json"
LEAD_SKILL="projects/LingWen1/skills/lingwen-project-lead.md"

if [[ -f .env ]]; then
  set -a
  set +u
  # shellcheck disable=SC1091
  source .env
  set -u
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "== 1/5 project preflight =="
butler project preflight --project "$PROJECT"

echo ""
echo "== 2/5 lead project + tool allowlist =="
python3 <<'PY'
from butler.project.lead import gateway_loop_role, is_lead_project
from butler.project.manager import get_project_manager
from butler.tools.project_tools import allowed_tool_names_for_project

pm = get_project_manager()
proj = pm.get_project("灵文1号")
assert proj is not None, "灵文1号 not registered"
assert is_lead_project("灵文1号", project=proj), "expected lead project"
assert gateway_loop_role("灵文1号", project=proj) == "lead"
allowed = allowed_tool_names_for_project(proj, role="lead")
assert allowed is not None
for name in ("read_file", "delegate_task", "run_workflow", "search_files"):
    assert name in allowed, f"missing lead tool: {name}"
for forbidden in ("patch", "terminal", "write_file"):
    assert forbidden not in allowed, f"lead must not have {forbidden}"
print("lead allowlist OK")
PY

echo ""
echo "== 3/5 workflow_state.json (read-only shape) =="
python3 <<PY
import json
from pathlib import Path
p = Path("$STATE_JSON")
data = json.loads(p.read_text(encoding="utf-8"))
keys = set(data.keys())
need_any = {"current_phase", "current_step", "project_status"} & keys
assert need_any, f"workflow_state missing phase/step keys: {sorted(keys)[:12]}"
print("workflow_state OK:", sorted(need_any))
PY

echo ""
echo "== 4/5 lead skill on disk =="
test -f "$LEAD_SKILL"

echo ""
echo "== 5/5 B1 dual-playbook static preflight =="
python3 <<'PY'
from butler.ops.dual_playbook_probe import run_dual_playbook_static_probe
out = run_dual_playbook_static_probe()
assert out["ok"], out.get("errors")
print("B1 static OK:", out["details"].get("workflow_phase"), out["details"].get("workflow_step"))
PY

echo ""
echo "LingWen lead smoke: ALL PASSED"
