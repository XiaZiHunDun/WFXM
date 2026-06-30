#!/usr/bin/env bash
# P2-G documentation hygiene gate — stale contradictions in docs.
# Usage: bash scripts/butler-p2g-doc-gate.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
check_absent() {
  local pattern="$1"
  local label="$2"
  shift 2
  if rg -q "$pattern" "$@"; then
    echo "FAIL: $label still matches in: $*"
    rg -n "$pattern" "$@" || true
    fail=1
  else
    echo "OK: no $label"
  fi
}

check_present() {
  local pattern="$1"
  local label="$2"
  shift 2
  if rg -q "$pattern" "$@"; then
    echo "OK: $label present"
  else
    echo "FAIL: expected $label in: $*"
    fail=1
  fi
}

echo "== P2-G documentation hygiene =="

# Stale test count narrative (positive claim only; negative mentions in P2-G SSOT are OK)
if rg -n '5040 tests.*(全部通过|all pass)' docs/ 2>/dev/null | rg -v 'project-optimization-directions-2026-06.md'; then
  echo "FAIL: stale 5040 tests pass narrative in docs/"
  fail=1
else
  echo "OK: no stale 5040 tests pass narrative"
fi

# Stale software-engineering-refactor header
check_absent '§3\.11 待写入' '§3.11 待写入' docs/

# v4-architecture current narrative
check_present '6250\+ passed' '6250+ test narrative' docs/architecture/v4-architecture.md

# DOCUMENTATION active index
check_present 'project-optimization-directions-2026-06' 'project-optimization in DOCUMENTATION' docs/DOCUMENTATION.md
check_present 'software-engineering-refactor-2026-06' 'software-engineering-refactor in DOCUMENTATION' docs/DOCUMENTATION.md

# Cursor rule workflow opt-in aligned with AGENTS.md
check_present 'BUTLER_WORKFLOW_AUTO_RESUME=1' 'workflow auto_resume in cursor rule' .cursor/rules/butler-v4-source-of-truth.mdc

# roadmap execution order should not use stale weekly calendar
check_absent '本周\s+PROD-P0-02' 'stale roadmap weekly calendar' docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md

# project-optimization P2-G done marker
check_present '方向 G.*done' 'P2-G done marker' docs/plans/active/project-optimization-directions-2026-06.md

if [[ "$fail" -ne 0 ]]; then
  echo "P2-G doc gate: FAILED"
  exit 1
fi
echo "P2-G doc gate: OK"
