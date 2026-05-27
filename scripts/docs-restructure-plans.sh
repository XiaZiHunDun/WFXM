#!/usr/bin/env bash
# Move docs/plans/*.md into subdirs (idempotent; skip if already moved).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
P="$ROOT/docs/plans"
mkdir -p "$P/active" "$P/decisions" "$P/roadmaps" "$P/comparisons" "$P/corpus" "$P/archive"

mv_file() {
  local f="$1" sub="$2"
  [[ -f "$P/$f" ]] || return 0
  git mv "$P/$f" "$P/$sub/$f"
}

for f in roadmap-backlog-and-boundaries-2026-05.md four-reports-out-of-scope-2026-05.md five-reports-not-done-2026-05.md; do
  mv_file "$f" decisions
done
for f in four-reports-improvement-roadmap-2026-05.md five-reports-improvement-roadmap-2026-05.md external-agent-reports-improvement-roadmap-2026-05.md; do
  mv_file "$f" roadmaps
done
for f in post-consolidation-roadmap-2026-05.md cc-butler-gap-analysis-2026-05.md; do
  mv_file "$f" active
done
for f in consolidation-2026-05.md consolidation-p3-implementation-2026-05.md memory-unification-implementation-2026-05.md \
  health-report-refactor-2026-05.md wechat-steer-implementation-2026-05.md p3-deferred-deep-dive-2026-05.md reference-learning-plan-2026-05.md; do
  mv_file "$f" archive
done
for f in "$P"/corpus-*.md "$P"/dev-assistant-corpus-*.md "$P"/wechat-corpus-ops-2026-05.md \
  "$P"/wechat-dev-conversation-scenarios-2026-05.md "$P"/wechat-real-coverage-matrix-2026-05.md \
  "$P"/wechat-real-dialogue-test-scenarios-2026-05.md; do
  [[ -f "$f" ]] || continue
  git mv "$f" "$P/corpus/$(basename "$f")"
done
for f in "$P"/*.md; do
  [[ "$(basename "$f")" == "README.md" ]] && continue
  git mv "$f" "$P/comparisons/$(basename "$f")"
done
echo "plans restructure: done"
