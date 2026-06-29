#!/usr/bin/env bash
# P5: Sample compaction before/after from session transcripts.
# Usage:
#   bash scripts/butler-compaction-audit-sample.sh
#   bash scripts/butler-compaction-audit-sample.sh 'wechat:user:proj'
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

PY="${BUTLER_PYTHON:-python3}"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

echo "== compaction audit sample =="
if [[ $# -gt 0 ]]; then
  "$PY" -m butler.ops.compaction_audit "$@"
else
  "$PY" -m butler.ops.compaction_audit
fi
