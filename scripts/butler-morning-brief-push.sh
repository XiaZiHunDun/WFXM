#!/usr/bin/env bash
# Push Owner morning brief (/简报 content) to WeChat when BUTLER_MORNING_BRIEF=1.
set -euo pipefail

ROOT="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
butler_source_env "$ROOT/.env" || true

# shellcheck source=scripts/lib/butler-systemd-install.sh
source "$ROOT/scripts/lib/butler-systemd-install.sh"
PY="$(butler_resolve_python3)"

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
