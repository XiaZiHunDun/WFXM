#!/usr/bin/env bash
# Push Owner morning brief (/简报 content) to WeChat when BUTLER_MORNING_BRIEF=1.
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

PY=python3
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

"$PY" - <<'PY'
import json
import sys

from butler.ops.morning_brief_push import morning_brief_enabled, push_morning_brief

if not morning_brief_enabled():
    print(json.dumps({"ok": False, "reason": "BUTLER_MORNING_BRIEF not enabled"}, ensure_ascii=False))
    sys.exit(0)

out = push_morning_brief()
print(json.dumps(out, ensure_ascii=False))
if not out.get("ok"):
    sys.exit(1)
PY
