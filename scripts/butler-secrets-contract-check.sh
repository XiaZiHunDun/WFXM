#!/usr/bin/env bash
# G1-13: unified secrets.yaml ↔ process env (extensions + platform contracts).
#
# Usage:
#   bash scripts/butler-secrets-contract-check.sh
#   bash scripts/butler-secrets-contract-check.sh --gateway-expected
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

if [[ "${BUTLER_SECRETS_CONTRACT_CHECK:-1}" == "0" ]]; then
  echo "skip: BUTLER_SECRETS_CONTRACT_CHECK=0"
  exit 0
fi

ARGS=()
if [[ "${BUTLER_SECRETS_GATEWAY_EXPECTED:-}" == "1" ]]; then
  ARGS+=(--gateway-expected)
fi

exec python3 -m butler.ops.secrets_contract_cli "${ARGS[@]}" "$@"
