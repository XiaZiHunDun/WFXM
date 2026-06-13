#!/usr/bin/env bash
# Exercise LingWen1 production failure → L3 experience capture (verify_fail with edits).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi
export BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES="${BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES:-1}"

python3 - <<'PY'
import json
import sys
from pathlib import Path

from butler.memory.memory_scope import project_coding_experiences_path
from butler.ops.lingwen1_capture_probe import run_lingwen1_capture_probe

out = run_lingwen1_capture_probe(force=True)
print(json.dumps(out, ensure_ascii=False, indent=2))
follow = out.get("experience_followup") or {}
if follow.get("action") != "upserted" or not follow.get("ok"):
    print("LingWen1 L3 capture: FAILED", file=sys.stderr)
    raise SystemExit(1)
save = follow.get("save_path") or ""
if save and Path(save).is_file():
    rows = json.loads(Path(save).read_text(encoding="utf-8"))
    prod_rows = [r for r in rows if str(r.get("id", "")).startswith("PROD_FAIL_")]
    print(f"L3 path={save} prod_fail_rows={len(prod_rows)}")
print("LingWen1 L3 capture: OK")
PY
