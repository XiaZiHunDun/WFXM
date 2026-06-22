#!/usr/bin/env bash
# Smoke: reasoning_step + reflect_step + verify_fail reflect + /诊断 lines (no LLM).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
export BUTLER_SESSION_TRANSCRIPT=1
export BUTLER_REASONING_TRACE=1

SK="smoke:reasoning:$(date +%s%N)"
python3 - <<PY
from types import SimpleNamespace

from butler.core.reasoning_trace import (
    format_reasoning_diagnostic_lines,
    record_reasoning_step,
    record_reflect_step,
    record_verify_fail_reflect,
)
from butler.core.session_transcript import load_transcript_tail

sk = "$SK"
record_reasoning_step(sk, phase="smoke", summary="smoke test reasoning summary", tool_intent="read_file")
record_reflect_step(sk, trigger="smoke", cause="demo", strategy="noop")
rows = load_transcript_tail(sk, max_lines=10)
types = {r.get("type") for r in rows}
assert "reasoning_step" in types, types
assert "reflect_step" in types, types
lines = format_reasoning_diagnostic_lines(sk)
assert any("推理摘要" in ln for ln in lines), lines
print("reasoning-trace-smoke: OK")
for ln in lines:
    print(f"  {ln}")

# verify_fail reflect path (dev_engine → transcript, no WeChat)
vf_sk = f"{sk}:verify_fail"
diag = SimpleNamespace(message="assert 1 == 2", rule="E999", source="pytest")
verify = SimpleNamespace(
    passed=False,
    diagnostics=[diag],
    output_tail="FAILED tests/test_demo.py::test_x",
    error_count=1,
)
state = SimpleNamespace(
    session_key=vf_sk,
    fix_count=1,
    max_fix_rounds=4,
    verify_result=verify,
    _last_fix_hint="structural: narrow patch",
    _coding_knowledge_ctx=None,
)
record_verify_fail_reflect(state, verify)
vf_rows = load_transcript_tail(vf_sk, max_lines=10)
vf_reflect = [r for r in vf_rows if r.get("type") == "reflect_step"]
assert len(vf_reflect) == 1, vf_rows
payload = vf_reflect[0].get("payload") or vf_reflect[0]
assert str(payload.get("trigger") or "") == "verify_fail", payload
vf_lines = format_reasoning_diagnostic_lines(vf_sk)
assert any("reflect=1" in ln for ln in vf_lines), vf_lines
assert any("最近反思" in ln and "assert 1 == 2" in ln for ln in vf_lines), vf_lines
print("verify-fail-reflect-smoke: OK")
for ln in vf_lines:
    print(f"  {ln}")
PY
