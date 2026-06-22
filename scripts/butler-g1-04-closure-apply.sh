#!/usr/bin/env bash
# G1-04 OT2 closure: patch gap register when closure check passes.
#
#   bash butler-g1-04-closure-apply.sh              # 需 ot2_closure_ready（生产硬反馈）
#   bash butler-g1-04-closure-apply.sh --pipeline-only  # 仅 B9 测评也可「管线已验」（OT2 未证）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PIPELINE_ONLY=0
if [[ "${1:-}" == "--pipeline-only" ]]; then
  PIPELINE_ONLY=1
fi

REGISTER="$ROOT/docs/plans/decisions/theory-implementation-gap-register-2026-06.md"
PILOT_LOG="$ROOT/projects/LingWen1/docs/pilot-log.md"

echo "== G1-04 closure check =="
if [[ "$PIPELINE_ONLY" == 1 ]]; then
  export PYTHONPATH="$ROOT"
  python3 - <<'PY' || { ec=$?; echo "closure-check failed (exit $ec); gap register 未改" >&2; exit "$ec"; }
import json
import sys
from butler.ops.boundary_observability import g1_04_observation_window_status
w = g1_04_observation_window_status()
print(json.dumps(w, ensure_ascii=False, indent=2))
if not w.get("pipeline_closure_ready"):
    print("G1-04: pipeline_closure_ready 未满足", file=sys.stderr)
    raise SystemExit(1)
if w.get("ot2_closure_ready"):
    print("G1-04: 已有生产证据 — 请用默认 apply（勿 --pipeline-only）", file=sys.stderr)
    raise SystemExit(2)
print("G1-04: pipeline-only closure — 管线已验，OT2 未证")
PY
else
  if ! bash "$ROOT/scripts/butler-g1-04-closure-check.sh"; then
    ec=$?
    echo "closure-check failed (exit $ec); gap register 未改" >&2
    exit "$ec"
  fi
fi

export PIPELINE_ONLY
echo ""
echo "== Patch gap register =="
export PYTHONPATH="$ROOT"
PILOT_NOTE="$(python3 - <<'PY'
import os
from datetime import date
from pathlib import Path

from butler.ops.boundary_observability import g1_04_observation_window_status

pipeline_only = os.environ.get("PIPELINE_ONLY") == "1"
w = g1_04_observation_window_status()
ws = w.get("window_start", "?")
we = w.get("window_end", "?")
today = date.today().isoformat()

if pipeline_only:
    new_row = (
        f"| G1-04 | OT2 有条件目标 | ✅ **管线已验**（窗 {ws}→{we}；"
        f"窗内 {w.get('feedback_in_window', 0)} 条仅 B9 测评；**OT2 收敛未证**） "
        f"| 硬反馈链路已通；待生产用量 | {today} pipeline-only |"
    )
    header_note = (
        f"> **真机/生产**：G1-04 试点窗已结案（{today}）；"
        "硬反馈管线已验；OT2 仍为有条件观测目标。"
    )
    pilot_note = "管线已验（仅 B9）；OT2 未证"
else:
    prod = w.get("feedback_evidence_production", 0)
    new_row = (
        f"| G1-04 | OT2 有条件目标 | ✅ **管线已验** + 生产硬反馈 {prod} 条（窗 {ws}→{we}；"
        f"OT2 仍为有条件观测目标） "
        f"| 窗满 + 生产证据 | {today} |"
    )
    header_note = (
        f"> **真机/生产**：G1-04 OT2 观测窗已结案（{today}）；含生产硬反馈。"
    )
    pilot_note = f"窗满 + 生产硬反馈 {prod} 条；OT2 仍观测"

path = Path("docs/plans/decisions/theory-implementation-gap-register-2026-06.md")
lines = path.read_text(encoding="utf-8").splitlines()
patched = False
out: list[str] = []
for line in lines:
    if line.startswith("| G1-04 | OT2"):
        if "✅ **管线已验**" in line or "✅ **已证**" in line:
            print("G1-04 already marked closed in register")
            raise SystemExit(0)
        out.append(new_row)
        patched = True
    elif "> **真机/生产**：仅 **G1-04** 仍开放" in line:
        out.append(header_note)
    else:
        out.append(line)

if not patched:
    raise SystemExit("G1-04 row not found — update register manually")

path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"Updated {path}")
print(pilot_note)
PY
)"
TODAY="$(date -I)"
PILOT_LINE="| $TODAY | G1-04 结案 | $PILOT_NOTE |"
echo ""
echo "== Pilot log =="
echo "$PILOT_LINE"

if [[ -f "$PILOT_LOG" ]]; then
  if ! grep -q "G1-04 结案" "$PILOT_LOG" 2>/dev/null; then
    echo "$PILOT_LINE" >> "$PILOT_LOG"
    echo "Appended to $PILOT_LOG"
  else
    echo "pilot-log already has G1-04 closure line"
  fi
fi

echo ""
echo "G1-04 closure apply done. Review diff and commit when ready."
