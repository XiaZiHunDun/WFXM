#!/usr/bin/env bash
# 委派 dev 链守门：patch → terminal(pytest) → git_status → commit（隔离仓库）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."
export BUTLER_ENABLE_TERMINAL=1
export BUTLER_TERMINAL_PROFILE=dev
export BUTLER_ENABLE_GIT=1
export BUTLER_ENABLE_GIT_WRITE=1
echo "== dev delegate workflow integration =="
python3 -m pytest tests/test_dev_tools_integration.py -q --tb=line
echo "Dev delegate smoke done."
