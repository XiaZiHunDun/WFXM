#!/usr/bin/env bash
# P1 handler probe: turn summary + DoT-lite edges + verify_fail reflect + /诊断 (no iLink).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

exec python3 <<PY
import json
import os
import sys
import time
from types import SimpleNamespace

ROOT = "$ROOT"
sys.path.insert(0, ROOT)

from butler.core.reasoning_trace import format_reasoning_diagnostic_lines, record_verify_fail_reflect
from butler.core.session_transcript import append_transcript_entry, record_reasoning_step
from butler.core.turn_summary_line import build_turn_summary_line, maybe_prepend_turn_summary, turn_summary_enabled
from butler.gateway.message_handler import ButlerMessageHandler
from butler.plan.markdown_sync import sync_plan_file_to_transcript
from butler.plan.mode import clear_plan_mode, set_plan_mode

OWNER = os.getenv("BUTLER_OWNER_WECHAT_ID", "owner-p1-probe")
SK = f"wechat:{OWNER}:p1-probe-{time.time_ns()}"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


assert turn_summary_enabled(), "BUTLER_TURN_SUMMARY_LINE default"
append_transcript_entry(SK, "user", {"content_preview": "读几个核心文档并总结"})
for path in ("docs/AGENTS.md", "docs/architecture/v4-architecture.md", "butler/main.py"):
    append_transcript_entry(
        SK,
        "tool_action",
        {"tool": "read_file", "args_preview": json.dumps({"path": path}), "source": "loop"},
    )
line = build_turn_summary_line(SK)
long_out = "长回复探针。" * 120
prepended = maybe_prepend_turn_summary(SK, long_out)
check("turn_summary line", bool(line and "读了3文件" in line), line or "")
check("turn_summary prepend", prepended.startswith("📎 ") and "读了3文件" in prepended)

set_plan_mode(SK, True)
md = """## 已知事实
- P1 probe 证据: handler

## 待验证
- [hypothesis] /诊断 连边

## 步骤
- [step] verify

## 风险
- 无
"""
n = sync_plan_file_to_transcript(SK, ".butler/plan/session-plan.md", md)
diag_lines = format_reasoning_diagnostic_lines(SK)
check(
    "dot-lite edges",
    n >= 4 and any("Plan 推理图" in ln and "0 边" not in ln for ln in diag_lines),
    str([ln for ln in diag_lines if "推理图" in ln]),
)

vf = SimpleNamespace(
    passed=False,
    diagnostics=[SimpleNamespace(message="assert 1 == 2")],
    output_tail="FAILED",
    error_count=1,
)
state = SimpleNamespace(
    session_key=SK,
    fix_count=1,
    max_fix_rounds=4,
    verify_result=vf,
    _last_fix_hint="narrow patch",
    _coding_knowledge_ctx=None,
)
record_verify_fail_reflect(state, vf)
record_reasoning_step(SK, phase="probe", summary="P1 probe reasoning")
check(
    "verify_fail reflect",
    any("reflect=1" in ln for ln in format_reasoning_diagnostic_lines(SK) if "推理摘要" in ln),
)

handler = ButlerMessageHandler(channel="gateway")
out = handler.handle_message("/诊断", session_key=SK, platform="wechat", external_id=OWNER) or ""
check("/诊断", ("诊断" in out or "Butler" in out) and ("推理摘要" in out or "Plan 推理图" in out))

clear_plan_mode(SK)
print(f"\np1-live-probe: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
