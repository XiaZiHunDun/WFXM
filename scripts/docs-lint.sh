#!/usr/bin/env bash
# Docs hygiene: stale status words + plans/*.md at root (should be in subdirs).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAIL=0

echo "== docs-lint: stale status in plans/ (exclude comparisons archive stubs) =="
# Stub redirect files may still contain 规划中 in historical quotes; scan active dirs only
if rg -n '规划中|提炼项未落地|待落地' docs/plans/active docs/plans/decisions docs/plans/roadmaps 2>/dev/null; then
  echo "FAIL: found stale planning status in active plan docs"
  FAIL=1
else
  echo "OK: no stale status in active/decisions/roadmaps"
fi

echo ""
echo "== docs-lint: flat plans/*.md (except README) =="
flat=$(find docs/plans -maxdepth 1 -name '*.md' ! -name README.md 2>/dev/null | wc -l)
if [[ "$flat" -gt 0 ]]; then
  echo "FAIL: plans/ root should only have README.md; found:"
  find docs/plans -maxdepth 1 -name '*.md' ! -name README.md
  FAIL=1
else
  echo "OK: plans/ root clean"
fi

echo ""
echo "== docs-lint: broken ../plans/ links (missing subdir) in docs/ =="
if rg -n '\]\(\.\./plans/[a-z0-9._-]+\.md\)' docs --glob '*.md' 2>/dev/null | head -20; then
  echo "FAIL: ../plans/<file>.md without active|decisions|roadmaps|comparisons|corpus|archive/"
  FAIL=1
else
  echo "OK: no bare ../plans/*.md in docs/"
fi

if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi
echo ""
echo "docs-lint: ALL PASSED"
