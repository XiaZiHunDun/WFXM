#!/usr/bin/env bash
# Seed + verify PROD_PLAYBOOK_* experiences (delegate rescue, path error, read_state).
#
# Usage:
#   bash scripts/butler-prod-playbook-seed.sh           # dry-run
#   bash scripts/butler-prod-playbook-seed.sh --apply   # write L4 tenant file
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help)
      sed -n '1,6p' "$0"
      exit 0
      ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

DRY=$([[ "$APPLY" -eq 1 ]] && echo 0 || echo 1)
export BUTLER_PROD_PLAYBOOK_DRY="$DRY"
python3 - <<'PY'
import os
import sys

from butler.dev_engine.prod_playbook_seeds import (
    seed_prod_playbooks,
    verify_prod_playbook_retrieval,
)

dry = os.environ.get("BUTLER_PROD_PLAYBOOK_DRY", "1").strip() not in ("0", "false", "no")
print("=== Prod playbook seed ===")
print(f"mode: {'dry-run' if dry else 'apply'}")
result = seed_prod_playbooks(dry_run=dry)
print(f"l4={result.get('l4_path')}")
print(f"added={result.get('added')} updated={result.get('updated')} total={result.get('total')}")

if dry:
    print()
    print("ACTION: re-run with --apply to persist L4 playbooks")
    sys.exit(0)

verify = verify_prod_playbook_retrieval()
print()
print("=== Retrieval verify ===")
for row in verify.get("checks") or []:
    tag = "PASS" if row.get("hit") else "FAIL"
    print(f"  [{tag}] {row.get('query')} -> {row.get('expected')} (top={row.get('top')})")
print(f"blocks_ok count={verify.get('block_count')}")
if not verify.get("ok"):
    print("FAIL: playbook retrieval incomplete")
    sys.exit(1)
print("OK: prod playbooks seeded and retrievable")
PY
