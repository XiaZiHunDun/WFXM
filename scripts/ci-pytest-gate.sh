#!/usr/bin/env bash
# Full pytest + coverage gate for CI (Python 3.11 matrix).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

# Stale parallel coverage shards break pytest-cov combine on shared workspaces.
rm -f .coverage
find . -maxdepth 1 -name '.coverage.*' -delete 2>/dev/null || true

python -m pytest --tb=short \
  --cov=butler \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=55 \
  -ra 2>&1 | tee pytest-output.txt
exit "${PIPESTATUS[0]}"
