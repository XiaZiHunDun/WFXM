#!/usr/bin/env bash
# Compare Pydantic JSON schemas under schemas/ with live model_json_schema() output.
# Usage:
#   bash scripts/check-schema-drift.sh           # warn-only (exit 0 on drift)
#   SCHEMA_DRIFT_STRICT=1 bash scripts/check-schema-drift.sh
#   bash scripts/check-schema-drift.sh --update-schemas
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${BUTLER_PYTHON:-python3}"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

UPDATE=0
for arg in "$@"; do
  case "$arg" in
    --update-schemas) UPDATE=1 ;;
    -h|--help)
      echo "Usage: $0 [--update-schemas]"
      exit 0
      ;;
  esac
done

declare -A MAP=(
  ["schemas/compaction/loop_compaction_view.v1.json"]="butler.contracts.compaction_ports:loop_compaction_view_schema_json"
  ["schemas/hook/hook_context_view.v1.json"]="butler.contracts.hook_context_ports:hook_context_view_schema_json"
  ["schemas/dev/dev_verify_view.v1.json"]="butler.contracts.dev_context_ports:dev_verify_view_schema_json"
  ["schemas/memory/loop_memory_view.v1.json"]="butler.contracts.memory_ports:loop_memory_view_schema_json"
  ["schemas/message/loop_api_message_view.v1.json"]="butler.contracts.message_ports:loop_api_message_view_schema_json"
  ["schemas/review/dev_review_view.v1.json"]="butler.contracts.review_ports:dev_review_view_schema_json"
)

drift=0
for path in "${!MAP[@]}"; do
  spec="${MAP[$path]}"
  mod="${spec%%:*}"
  fn="${spec##*:}"
  live="$("$PY" -c "import importlib; m=importlib.import_module('${mod}'); print(getattr(m,'${fn}')(), end='')")"
  if [[ ! -f "$path" ]]; then
    echo "MISSING schema file: $path"
    drift=$((drift + 1))
    if [[ "$UPDATE" -eq 1 ]]; then
      mkdir -p "$(dirname "$path")"
      printf '%s' "$live" >"$path"
      echo "WROTE $path"
    fi
    continue
  fi
  if ! diff -q <(printf '%s' "$live") "$path" >/dev/null 2>&1; then
    echo "DRIFT: $path (run with --update-schemas after ADR/CHANGELOG note)"
    drift=$((drift + 1))
    if [[ "$UPDATE" -eq 1 ]]; then
      printf '%s' "$live" >"$path"
      echo "UPDATED $path"
      drift=$((drift - 1))
    fi
  fi
done

if [[ "$drift" -gt 0 ]]; then
  if [[ "${SCHEMA_DRIFT_STRICT:-0}" == "1" ]]; then
    echo "check-schema-drift: $drift issue(s) (strict)"
    exit 1
  fi
  echo "check-schema-drift: WARN $drift drift(s) (set SCHEMA_DRIFT_STRICT=1 to fail)"
  exit 0
fi
echo "check-schema-drift: OK"
