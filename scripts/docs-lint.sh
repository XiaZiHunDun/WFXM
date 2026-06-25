#!/usr/bin/env bash
# Docs hygiene: stale status words, plans layout, broken links, dead env keys.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAIL=0
DOCS_LINT_PY="$(command -v python || command -v python3 || true)"

_docs_lint_require_tools() {
  if [[ -z "$DOCS_LINT_PY" ]]; then
    echo "FAIL: python3/python not found (install Python or use actions/setup-python)"
    exit 1
  fi
  if ! command -v rg >/dev/null 2>&1; then
    echo "FAIL: ripgrep (rg) not found (apt install ripgrep / brew install ripgrep)"
    exit 1
  fi
}

_docs_lint_stale_status() {
  echo "== docs-lint: stale status in plans/ (exclude comparisons archive stubs) =="
  if rg -n '规划中|提炼项未落地|待落地' docs/plans/active docs/plans/decisions docs/plans/roadmaps 2>/dev/null; then
    echo "FAIL: found stale planning status in active plan docs"
    return 1
  fi
  echo "OK: no stale status in active/decisions/roadmaps"
}

_docs_lint_flat_plans() {
  echo ""
  echo "== docs-lint: flat plans/*.md (except README) =="
  local flat
  flat=$(find docs/plans -maxdepth 1 -name '*.md' ! -name README.md 2>/dev/null | wc -l)
  if [[ "$flat" -gt 0 ]]; then
    echo "FAIL: plans/ root should only have README.md; found:"
    find docs/plans -maxdepth 1 -name '*.md' ! -name README.md
    return 1
  fi
  echo "OK: plans/ root clean"
}

_docs_lint_bare_plans_links() {
  echo ""
  echo "== docs-lint: broken ../plans/ links (missing subdir) in docs/ =="
  if rg -n '\]\(\.\./plans/[a-z0-9._-]+\.md\)' docs --glob '*.md' 2>/dev/null | head -20; then
    echo "FAIL: ../plans/<file>.md without active|decisions|roadmaps|comparisons|corpus|archive/"
    return 1
  fi
  echo "OK: no bare ../plans/*.md in docs/"
}

_docs_lint_broken_links() {
  echo ""
  echo "== docs-lint: broken relative links in docs/ =="
  if ! "${DOCS_LINT_PY}" - <<'PYEOF'
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
            if target.endswith("pilot-log.md") or "/pilot-log.md" in target:
                continue
            if "/tests/corpus/" in target:
                continue
            norm = target.replace("\\", "/")
            if norm.startswith("../reference") or norm.startswith("reference/") or norm == "../reference" or norm == "../reference/":
                continue
            if "/history/" in norm or norm.startswith("../history/") or norm.startswith("history/"):
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(fpath), target))
            if resolved.startswith("docs/history") or resolved in ("reference", "docs/reference"):
                continue
            if not os.path.exists(resolved):
                broken.append("  {} -> {}".format(fpath, target))
if broken:
    for b in sorted(set(broken)):
        print(b)
    sys.exit(1)
PYEOF
  then
    echo "FAIL: broken relative links found"
    return 1
  fi
  echo "OK: no broken relative links"
}

_docs_lint_env_counts() {
  echo ""
  echo "== docs-lint: reference.md vs .env.example env var consistency =="
  bash scripts/check-env-reference-sync.sh
}

_docs_lint_dead_env() {
  echo ""
  echo "== docs-lint: dead env keys (reference.md vs butler/ readers) =="
  bash scripts/check-dead-env.sh
}

_run_section() {
  local name=$1
  shift
  if ! "$@"; then
    echo "docs-lint: section FAILED ($name)"
    FAIL=1
  fi
}

case "${1:-all}" in
  stale-status) _docs_lint_require_tools; _docs_lint_stale_status ;;
  flat-plans) _docs_lint_require_tools; _docs_lint_flat_plans ;;
  bare-plans-links) _docs_lint_require_tools; _docs_lint_bare_plans_links ;;
  broken-links) _docs_lint_require_tools; _docs_lint_broken_links ;;
  dead-env) _docs_lint_require_tools; _docs_lint_env_counts; _docs_lint_dead_env ;;
  all)
    _docs_lint_require_tools
    _run_section stale-status _docs_lint_stale_status
    _run_section flat-plans _docs_lint_flat_plans
    _run_section bare-plans-links _docs_lint_bare_plans_links
    _run_section broken-links _docs_lint_broken_links
    _docs_lint_env_counts || true
    _run_section dead-env _docs_lint_dead_env
    if [[ "$FAIL" -ne 0 ]]; then
      echo ""
      echo "docs-lint: FAILED (see sections above marked FAIL)"
      exit 1
    fi
    echo ""
    echo "docs-lint: ALL PASSED"
    ;;
  -h|--help|help)
    echo "Usage: $0 [all|stale-status|flat-plans|bare-plans-links|broken-links|dead-env]"
    ;;
  *)
    echo "Unknown docs-lint section: $1" >&2
    exit 2
    ;;
esac
