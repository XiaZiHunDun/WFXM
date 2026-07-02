#!/usr/bin/env bash
# P3-H unified recall rollout verify — handler sim + health report + CLI (no iLink).
#
# Usage:
#   bash scripts/butler-p3h-rollout-verify.sh
#   bash scripts/butler-p3h-rollout-verify.sh --with-hermes   # also run hermes-rollout sim
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

WITH_HERMES=0
for arg in "$@"; do
  case "$arg" in
    --with-hermes) WITH_HERMES=1 ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

if [[ "$WITH_HERMES" == "1" ]]; then
  bash "$ROOT/scripts/butler-hermes-rollout-wechat-sim.sh"
fi

exec python3 - <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from butler.config import get_butler_home, reload_butler_settings

reload_butler_settings()
owner = (os.getenv("BUTLER_OWNER_WECHAT_ID") or "").strip()
if not owner:
    print("FAIL: BUTLER_OWNER_WECHAT_ID not set")
    raise SystemExit(1)

failures: list[str] = []
sk = f"wechat:{owner}:p3h-verify-{time.time_ns()}"


def ok(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  [ok] {name}" + (f" — {detail}" if detail else ""))
    else:
        failures.append(name)
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


print("=== P3-H rollout verification ===")
for key in (
    "BUTLER_MEMORY_OBSERVER_QUEUE",
    "BUTLER_MEMORY_OBSERVATION_RECALL",
    "BUTLER_MEMORY_UNIFIED_RECALL",
    "BUTLER_SEMANTIC_MEMORY",
):
    print(f"  {key}={os.getenv(key, '')!r}")

from butler.gateway.message_handler import ButlerMessageHandler
from butler.memory.butler_memory import ButlerMemory
from butler.memory.owner_write_pending import (
    approve_owner_pending,
    queue_owner_write,
    reject_all_owner_pending,
)
from butler.memory.vector_sync_telemetry import get_vector_sync_times
from butler.ops.health_report import (
    HealthReportInput,
    build_health_report,
    collect_mem_stats_for_health,
)
from butler.orchestrator import ButlerOrchestrator

reject_all_owner_pending()
bm = ButlerMemory(get_butler_home())
queue_owner_write(scope="owner_profile", content="p3h-rollout-verify: vector sync")
approve_owner_pending(0, bm)
ok("vector sync telemetry", "owner_profile" in get_vector_sync_times())

orch = ButlerOrchestrator()
health: dict = {}
full = build_health_report(
    HealthReportInput(
        session_key=sk,
        health=health,
        tool_summary={"total": 0, "failed": 0, "codes": []},
        mem_stats=collect_mem_stats_for_health(orch, sk, health),
        orchestrator=orch,
    )
)
ok("统一 hybrid 召回: 开", "统一 hybrid 召回: 开" in full)
ok("observation 辅助召回: 开", "observation 辅助召回: 开" in full)
ok("最近向量写入", "最近向量写入" in full and "owner_profile" in full)

handler = ButlerMessageHandler(channel="gateway")
detail = handler.handle_message(
    "/诊断 详细", session_key=sk, platform="wechat", external_id=owner
) or ""
ok("wechat /诊断 详细", "诊断" in detail and ("附件" in detail or "…" in detail))

root = os.getcwd()
env = {**os.environ, "PYTHONPATH": root}
py = sys.executable


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [py, "butler/main.py", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )


for label, cli_args in (
    ("hybrid CLI", ["memory", "search", "pytest", "--scope", "hybrid", "--project", "演示试点", "--limit", "3", "--json"]),
    ("observation CLI", ["memory", "search", "read_file", "--scope", "observation", "--project", "灵文1号", "--limit", "3", "--json"]),
):
    proc = run_cli(cli_args)
    try:
        data = json.loads(proc.stdout)
        ok(label, data.get("ok") is True)
    except json.JSONDecodeError:
        ok(label, False, (proc.stderr or proc.stdout)[:160])

ok("butler doctor", run_cli(["doctor"]).returncode == 0)

print(f"\np3h-rollout-verify: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
