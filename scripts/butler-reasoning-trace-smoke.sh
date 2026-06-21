#!/usr/bin/env bash
# Smoke: reasoning_step + reflect_step transcript + /诊断 lines (no LLM).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
export BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
export BUTLER_SESSION_TRANSCRIPT=1
export BUTLER_REASONING_TRACE=1

SK="smoke:reasoning:$(date +%s)"
python3 - <<PY
from butler.core.reasoning_trace import (
    format_reasoning_diagnostic_lines,
    record_reasoning_step,
    record_reflect_step,
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
PY
