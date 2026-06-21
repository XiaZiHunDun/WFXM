#!/usr/bin/env bash
# G1-04 OT2 closure: run on/after 2026-06-23 when butler-g1-04-closure-check.sh exits 0.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REGISTER="$ROOT/docs/plans/decisions/theory-implementation-gap-register-2026-06.md"
PILOT_LOG="$ROOT/projects/LingWen1/docs/pilot-log.md"

echo "== G1-04 closure check =="
if ! bash "$ROOT/scripts/butler-g1-04-closure-check.sh"; then
  ec=$?
  echo "closure-check failed (exit $ec); gap register 未改" >&2
  exit "$ec"
fi

echo ""
echo "== Patch gap register =="
export PYTHONPATH="$ROOT"
python3 - <<'PY'
from pathlib import Path

path = Path("docs/plans/decisions/theory-implementation-gap-register-2026-06.md")
lines = path.read_text(encoding="utf-8").splitlines()
new_row = (
    "| G1-04 | OT2 有条件目标 | ✅ **已证**（窗 06-09→06-23；窗内 feedback≥1） "
    "| OT2 closure_ready | 2026-06-23 结案 |"
)
patched = False
out: list[str] = []
for line in lines:
    if line.startswith("| G1-04 | OT2"):
        if "✅ **已证**" in line:
            print("G1-04 already marked closed in register")
            raise SystemExit(0)
        out.append(new_row)
        patched = True
    elif "> **真机/生产**：仅 **G1-04** 仍开放" in line:
        out.append("> **真机/生产**：G1-04 OT2 观测窗已结案（2026-06-23）。")
    else:
        out.append(line)

if not patched:
    raise SystemExit("G1-04 row not found — update register manually")

path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"Updated {path}")
PY

echo ""
TODAY="$(date -I)"
PILOT_LINE="| $TODAY | G1-04 结案 | OT2 观测窗满；closure_ready；认知层 CoT/DoT-lite 试点可归档 |"
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
