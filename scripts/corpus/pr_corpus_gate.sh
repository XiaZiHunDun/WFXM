#!/usr/bin/env bash
# Run unified corpus mock when PR touches gateway routing or corpus files.
set -euo pipefail
cd "$(dirname "$0")/../.."

GATE_PATHS=(
  butler/gateway/message_handler.py
  butler/gateway/
  tests/corpus/
  tests/test_gateway_dev_conversations.py
)

if [[ "${CORPUS_PR_GATE_FORCE:-}" == "1" ]]; then
  echo "==> corpus pr-gate (forced)"
  exec "$(dirname "$0")/../corpus-test.sh" unified "$@"
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Not a git repo; skip pr-gate"
  exit 0
fi

BASE="${CORPUS_PR_GATE_BASE:-origin/main}"
if ! git rev-parse "$BASE" >/dev/null 2>&1; then
  BASE="HEAD~1"
fi

CHANGED="$(git diff --name-only "$BASE"...HEAD 2>/dev/null || git diff --name-only HEAD)"
needs=0
for p in "${GATE_PATHS[@]}"; do
  if echo "$CHANGED" | grep -q "^${p}"; then
    needs=1
    break
  fi
done

if [[ "$needs" -eq 0 ]]; then
  echo "pr-gate: no corpus/gateway paths in diff ($BASE...HEAD); skip"
  exit 0
fi

echo "==> corpus pr-gate: corpus + gateway mock (diff vs $BASE)"
exec "$(dirname "$0")/../corpus-test.sh" unified "$@"
