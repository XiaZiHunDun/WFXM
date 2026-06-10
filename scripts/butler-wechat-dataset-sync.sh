#!/usr/bin/env bash
# O8: Sync WeChat utterance corpus to LangFuse datasets.
#
# Usage:
#   bash scripts/butler-wechat-dataset-sync.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

python3 - <<'PY'
import json
from butler.ops.wechat_dataset import load_and_push_wechat_dataset

summary = load_and_push_wechat_dataset()
print(json.dumps(summary, ensure_ascii=False, indent=2))
if not summary.get("single_turn_items") and not summary.get("multi_turn_items"):
    raise SystemExit("No corpus items found to sync")
PY
