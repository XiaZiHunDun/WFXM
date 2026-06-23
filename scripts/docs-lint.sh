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

echo ""
echo "== docs-lint: broken relative links in docs/ =="
python3 - <<'PYEOF'
import re, os, sys
broken = []
for root, dirs, files in os.walk("docs"):
    if root.startswith("docs/history"):
        continue
    for fname in files:
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(root, fname)
        with open(fpath) as f:
            content = f.read()
        for m in re.finditer(r"\]\(([^)]+)\)", content):
            target = m.group(1).split("#")[0]
            if not target or target.startswith("http"):
                continue
            if "(?!" in target or "(?<" in target or target.startswith("?"):
                continue
            if "reference/" in target and ("hermes" in target or "opencode" in target or "openclaw" in target or "oh-my-" in target):
                continue
            if ".butler/" in target or target.startswith("../../.butler/"):
                continue
            if "/tests/corpus/" in target:
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(fpath), target))
            if not os.path.exists(resolved):
                broken.append("  {} -> {}".format(fpath, target))
if broken:
    for b in sorted(set(broken)):
        print(b)
    sys.exit(1)
PYEOF
if [[ $? -ne 0 ]]; then
  echo "FAIL: broken relative links found"
  FAIL=1
else
  echo "OK: no broken relative links"
fi

echo ""
echo "== docs-lint: reference.md vs .env.example env var consistency =="
REF_VARS=$(rg -o 'BUTLER_[A-Z_]+' docs/config/reference.md 2>/dev/null | sort -u | wc -l)
ENV_VARS=$(rg -o 'BUTLER_[A-Z_]+' .env.example 2>/dev/null | sort -u | wc -l)
echo "reference.md env vars: $REF_VARS / .env.example env vars: $ENV_VARS"

echo ""
echo "== docs-lint: dead env keys (reference.md vs butler/ readers) =="
if ! bash scripts/check-dead-env.sh; then
  FAIL=1
fi

if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi
echo ""
echo "docs-lint: ALL PASSED"
