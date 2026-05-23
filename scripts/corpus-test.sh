#!/usr/bin/env bash
# Corpus evaluation helper — tests/corpus/
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

MODE="${1:-mock}"
case "$MODE" in
  mock)
    exec python3 -m pytest tests/corpus -m "corpus and corpus_mock" -q "$@"
    ;;
  smoke)
    set -a
    # shellcheck source=/dev/null
    source .env 2>/dev/null || true
    set +a
    export BUTLER_RUN_REAL_API_SMOKE=1
    exec python3 -m pytest tests/corpus/runners/test_agent_loop_rubric.py \
      -m "corpus_live and corpus_smoke" -v "$@"
    ;;
  live)
    set -a
    # shellcheck source=/dev/null
    source .env 2>/dev/null || true
    set +a
    export BUTLER_RUN_REAL_API_SMOKE=1
    export CORPUS_ARCHIVE="${CORPUS_ARCHIVE:-1}"
    exec python3 -m pytest tests/corpus/runners/test_agent_loop_rubric.py \
      -m corpus_live -v "$@"
    ;;
  gateway)
    exec python3 -m pytest tests/test_gateway_dev_conversations.py -q "$@"
    ;;
  *)
    echo "Usage: $0 {mock|smoke|live|gateway}" >&2
    exit 1
    ;;
esac
