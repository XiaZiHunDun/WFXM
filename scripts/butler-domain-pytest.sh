#!/usr/bin/env bash
# Run pytest for one or more test domains (gateway | ops | dev_engine | memory | core | tools | runtime | all).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

DOMAINS=("$@")
if [[ ${#DOMAINS[@]} -eq 0 ]]; then
  DOMAINS=(gateway ops dev_engine memory core)
fi

paths=()
for d in "${DOMAINS[@]}"; do
  case "$d" in
    all)
      PY="$(command -v python || command -v python3)"
      exec "${PY}" -m pytest tests/ -q --tb=line
      ;;
    gateway|ops|dev_engine|memory|core|tools|runtime|io|transport|hooks)
      if [[ -d "tests/$d" ]]; then
        paths+=("tests/$d/")
      else
        echo "unknown or missing domain: $d" >&2
        exit 2
      fi
      ;;
    *)
      echo "Usage: $0 [gateway|ops|dev_engine|memory|core|tools|runtime|all ...]" >&2
      exit 2
      ;;
  esac
done

PYTHON_BIN="$(command -v python || command -v python3)"
"${PYTHON_BIN}" -m pytest "${paths[@]}" -q --tb=line