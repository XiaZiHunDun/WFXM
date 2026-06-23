#!/usr/bin/env bash
# Head-to-head: Butler dev delegate vs Claude Code CLI.
#
# Usage:
#   bash scripts/butler-head-to-head.sh t1|t2
#   bash scripts/butler-head-to-head.sh t2 --butler-only
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

SCENARIO="${1:-t1}"
shift || true
BUTLER_ONLY=0
CC_ONLY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --butler-only) BUTLER_ONLY=1 ;;
    --cc-only) CC_ONLY=1 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/scripts/lib/butler-source-env.sh" 2>/dev/null || true
  butler_source_env "$ROOT/.env" 2>/dev/null || true
  set +a
fi

exec python3 - "$SCENARIO" "$BUTLER_ONLY" "$CC_ONLY" <<'PY'
import json
import sys

from butler.ops.head_to_head import SCENARIOS

key = sys.argv[1].strip().lower()
butler_only = sys.argv[2] == "1"
cc_only = sys.argv[3] == "1"
scenario = SCENARIOS.get(key)
if scenario is None:
    raise SystemExit(f"unknown scenario: {key!r} (use: {', '.join(SCENARIOS)})")

from butler.ops.head_to_head_common import run_scenario

out = run_scenario(scenario, live=True, butler_only=butler_only, cc_only=cc_only)
print(json.dumps(out, ensure_ascii=False, indent=2))
s = out.get("summary") or {}
print()
print(f"=== {key.upper()} head-to-head summary ===")
if "butler" in out:
    b = out["butler"]
    print(
        f"Butler: pytest={b.get('pytest_green')} verify={b.get('verify_passed')} "
        f"task={b.get('task_id')} elapsed={b.get('elapsed_seconds')}s"
    )
if "cc" in out:
    c = out["cc"]
    print(
        f"CC CLI:  pytest={c.get('pytest_green')} turns={c.get('num_turns')} "
        f"elapsed={c.get('elapsed_seconds')}s"
    )
if not butler_only and not cc_only:
    if s.get("butler_pytest_green") and s.get("cc_pytest_green"):
        print("OK: both sides green")
    else:
        print("WARN: not both green", file=sys.stderr)
        raise SystemExit(1)
PY
