#!/usr/bin/env bash
# Capability baseline: read / delegate / workflow 三件套季度跑分（AP 五维 Capability）
# Usage: bash scripts/butler-capability-baseline.sh [--archive] [--log]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

LOG=0
ARCHIVE=0
for arg in "$@"; do
  case "$arg" in
    --log) LOG=1 ;;
    --archive) ARCHIVE=1 ;;
    -h|--help)
      sed -n '1,5p' "$0"
      exit 0
      ;;
  esac
done

OUT="$ROOT/.butler/reports/capability-baseline.json"
mkdir -p "$(dirname "$OUT")"

echo "== Capability baseline =="
FAIL=0

echo "-- TCR (strict production + boundaries) --"
bash "$ROOT/scripts/butler-trajectory-compliance-gate.sh" --warn-only || FAIL=1

echo "-- B1 dual-playbook static --"
bash "$ROOT/scripts/butler-wechat-dual-playbook-probe.sh" --static-only || FAIL=1

echo "-- L-B delegate/workflow fixtures (mock LLM) --"
python -m pytest tests/test_llm_response_fixtures.py -q --tb=line || FAIL=1

OK=$([[ "$FAIL" -eq 0 ]] && echo True || echo False)
python - <<PY
import json
import time
from pathlib import Path

out = Path("$OUT")
report = {
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "ok": $OK,
    "components": ["tcr", "dual_playbook_static", "llm_response_fixtures"],
}
tcr = Path("$ROOT/.butler/reports/tcr-latest.json")
if tcr.is_file():
    report["tcr"] = json.loads(tcr.read_text(encoding="utf-8"))
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"-> {out}")
PY

if [[ "$ARCHIVE" -eq 1 && -f "$OUT" ]]; then
  ARCHIVE_DIR="$ROOT/.butler/reports/archive"
  mkdir -p "$ARCHIVE_DIR"
  Q=$(( (10#$(date +%m) - 1) / 3 + 1 ))
  ARCHIVE_PATH="$ARCHIVE_DIR/capability-baseline-$(date +%Y)-Q${Q}.json"
  cp "$OUT" "$ARCHIVE_PATH"
  echo "-> archived $ARCHIVE_PATH"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "Capability baseline: FAIL"
  exit 1
fi
echo "Capability baseline: OK"
