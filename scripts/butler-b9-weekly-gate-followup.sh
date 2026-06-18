#!/usr/bin/env bash
# B9 weekly learning + SWE full LIVE when two-week gate opens.
#
# 1. Tier-1 LIVE + Tier-2 probe + SWE subset + prod snapshot (records weekly snapshot)
# 2. If evaluate_swe_full_entry_gate().allowed → run full 15-instance LIVE (no --force)
#
# Usage:
#   bash scripts/butler-b9-weekly-gate-followup.sh
#   BUTLER_B9_WEEKLY_MODEL=deepseek/deepseek-reasoner bash scripts/butler-b9-weekly-gate-followup.sh
# Cron (ISO week 25+ Sunday 03:30 — see install-butler-b9-weekly-timer.sh):
#   30 3 * * 0 cd /path/to/WFXM && bash scripts/butler-b9-weekly-gate-followup.sh
set -euo pipefail

ROOT="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_EVAL_LLM_BENCHMARK="${BUTLER_EVAL_LLM_BENCHMARK:-1}"

MODEL="${BUTLER_B9_WEEKLY_MODEL:-minimax/MiniMax-M3}"
LOG="${BUTLER_B9_WEEKLY_LOG:-$ROOT/logs/butler-b9-weekly-gate.log}"
mkdir -p "$(/usr/bin/dirname "$LOG")"

# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
butler_source_env "$ROOT/.env" || true

# shellcheck source=scripts/lib/butler-systemd-install.sh
source "$ROOT/scripts/lib/butler-systemd-install.sh"
PY="$(butler_resolve_python3)"

echo "=== B9 weekly-gate followup: model=$MODEL ===" | tee -a "$LOG"
bash "$ROOT/scripts/butler-b9-weekly-learning.sh" "$MODEL" 2>&1 | tee -a "$LOG"

"$PY" - <<PY | tee -a "$LOG"
import json
import os
import subprocess
import sys

from butler.ops.swebench_entry_gate import evaluate_swe_full_entry_gate

gate = evaluate_swe_full_entry_gate()
print()
print("=== SWE full-entry gate ===")
print(json.dumps(gate, ensure_ascii=False, indent=2))
if not gate.get("allowed"):
    print(f"SWE full LIVE deferred: {gate.get('reason')}")
    sys.exit(0)

print("Gate OPEN — running full SWE-bench Lite LIVE (15 instances, no --force)")
root = os.environ.get("ROOT_OVERRIDE") or "${ROOT}"
env = os.environ.copy()
env["BUTLER_EVAL_LLM_BENCHMARK"] = "1"
env["PYTHONPATH"] = root
rc = subprocess.call(
    ["bash", os.path.join(root, "scripts", "butler-eval-swebench-live-full.sh")],
    cwd=root,
    env=env,
)
if rc != 0:
    print("SWE full LIVE failed", file=sys.stderr)
sys.exit(rc)
PY
