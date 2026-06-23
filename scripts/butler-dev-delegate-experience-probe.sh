#!/usr/bin/env bash
# Read-only: dev delegate sim vs coding experience extraction gates (L3/L4).
#
# Sim content/review delegates do NOT write coding_experiences — extraction runs only
# on dev_engine success path (_try_extract_experience in delegate_phases).
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

python3 - <<'PY'
import json
import os
from pathlib import Path

from butler.config import get_butler_home
from butler.dev_engine.dev_tools import dev_engine_enabled
from butler.memory.memory_scope import (
    project_coding_experiences_path,
    tenant_coding_experiences_path,
)
from butler.project.manager import get_project_manager

print("=== Dev delegate sim · experience extraction probe ===")
print()

de = dev_engine_enabled()
term = os.getenv("BUTLER_ENABLE_TERMINAL", "").strip() in ("1", "true", "yes", "on")
print(f"1. BUTLER_DEV_ENGINE={'on' if de else 'off'}  BUTLER_ENABLE_TERMINAL={'on' if term else 'off'}")
print("   Gates: dev role + DevPhase.DONE + verify_result.passed + edit snippets>20 + activated theorems")
print("   Sim content/review: no dev_engine path → no L3 auto-extract (expected)")
print("   Sim dev py_compile: may extract only if dev_engine on AND verify passes on code edits")
print()

home = Path(get_butler_home())
l4 = tenant_coding_experiences_path(home)
l4_n = 0
if l4.is_file():
    try:
        l4_n = len(json.loads(l4.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        l4_n = -1
print(f"2. L4 tenant: {l4} entries={l4_n}")

pm = get_project_manager()
for name in ("灵文1号", "演示试点"):
    proj = pm.get_project(name)
    ws = getattr(proj, "workspace", None) if proj else None
    if not ws:
        print(f"3. {name}: workspace missing")
        continue
    l3 = project_coding_experiences_path(Path(ws))
    n = 0
    if l3.is_file():
        try:
            rows = json.loads(l3.read_text(encoding="utf-8"))
            n = len(rows) if isinstance(rows, list) else len(rows.get("experiences", []))
        except json.JSONDecodeError:
            n = -1
    print(f"3. L3 {name}: {l3} entries={n}")

print()
print("OK: probe complete (informational; sim success does not require L3 growth)")
PY
