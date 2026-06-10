#!/usr/bin/env bash
# R8-6: flag BUTLER_* keys in reference.md with no string occurrence in butler/ (reader or default).
set -euo pipefail
cd "$(dirname "$0")/.."

ALLOWLIST_EXACT='BUTLER_RUNTIME_RUN_CONSISTENCY|BUTLER_RUNTIME_SMOKE_PUSH|BUTLER_RUN_REAL_API_SMOKE|BUTLER_HOOK_EVENT|BUTLER_HOOK_INPUT|BUTLER_HOOK_TOOL|BUTLER_NOTIFY_URLS|BUTLER_WORKFLOW_HANDOFF_ONLY|BUTLER_DISABLE_EXPERIMENTAL_CACHE'

# Prose wildcards / examples (not real env names).
SKIP_REGEX='_\*$|_$|FOO$'

dead=0
while read -r env; do
  [[ -z "$env" ]] && continue
  if echo "$env" | grep -qE "$SKIP_REGEX"; then
    continue
  fi
  if [[ "$env" == BUTLER_SMOKE_* ]]; then
    continue
  fi
  if echo "$env" | grep -qE "^($ALLOWLIST_EXACT)$"; then
    continue
  fi
  if rg -qF "$env" butler/ 2>/dev/null; then
    continue
  fi
  echo "DEAD (no butler/ reader): $env"
  dead=$((dead + 1))
done < <(rg -o 'BUTLER_[A-Z0-9_]+' docs/config/reference.md | sort -u)

if [[ "$dead" -gt 0 ]]; then
  echo "check-dead-env: $dead issue(s)"
  exit 1
fi
echo "check-dead-env: OK"
