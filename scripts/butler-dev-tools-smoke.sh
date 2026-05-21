#!/usr/bin/env bash
# Dev tools integration smoke (git / terminal / patch) in isolated temp workspace.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."
echo "== dev workflow integration (isolated workspace) =="
export BUTLER_ENABLE_TERMINAL=1
export BUTLER_TERMINAL_PROFILE=dev
export BUTLER_ENABLE_GIT=1
export BUTLER_ENABLE_GIT_WRITE=1
python3 -m pytest tests/test_dev_tools_integration.py -q --tb=short

echo ""
echo "== git / P2 unit tests (default env gates) =="
unset BUTLER_ENABLE_GIT BUTLER_ENABLE_GIT_WRITE BUTLER_ENABLE_TERMINAL || true
python3 -m pytest tests/test_git_tools.py tests/test_dev_ops_p2.py -q --tb=line

echo ""
echo "Dev tools smoke done."
