#!/usr/bin/env bash
# Phase 1 observability provisioning — LangFuse + embedding production defaults.
# Idempotent: only sets vars that are missing or still commented defaults.
#
# Usage:
#   bash scripts/butler-observability-provision.sh
#   bash scripts/butler-observability-provision.sh --check-only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
CHECK_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY=1 ;;
    -h|--help)
      echo "Usage: $0 [--check-only]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

_set_env_var() {
  local key="$1" value="$2"
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "  SKIP $key (no $ENV_FILE)"
    return
  fi
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    local current
    current=$(grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2-)
    if [[ -n "$current" && "$current" != "0" ]]; then
      echo "  KEEP $key=$current"
      return
    fi
  fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    echo "  NEED $key=$value"
    return
  fi
  if grep -qE "^#? *${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i -E "s|^#? *${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
  echo "  SET  $key=$value"
}

_ensure_langfuse_project() {
  local proj_dir="$BUTLER_HOME/projects/butler-v4"
  local cfg="$proj_dir/langfuse.json"
  if [[ -f "$cfg" ]]; then
    echo "  KEEP $cfg"
    return
  fi
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    echo "  NEED $cfg"
    return
  fi
  mkdir -p "$proj_dir"
  cat > "$cfg" <<'JSON'
{
  "project_name": "butler-v4",
  "project_id": "butler-v4",
  "langfuse_host": "http://localhost:3000",
  "langfuse_public_key": "pk-butler-dev",
  "langfuse_secret_key": "sk-butler-dev"
}
JSON
  echo "  SET  $cfg"
}

echo "=== Butler Observability Provision ==="
echo "  .env: $ENV_FILE"
echo ""

echo "[LangFuse]"
_set_env_var "BUTLER_LANGFUSE_ENABLED" "1"
_set_env_var "LANGFUSE_HOST" "http://localhost:3000"
_set_env_var "LANGFUSE_PUBLIC_KEY" "pk-butler-dev"
_set_env_var "LANGFUSE_SECRET_KEY" "sk-butler-dev"
_ensure_langfuse_project
echo ""

echo "[Embedding]"
_set_env_var "BUTLER_SEMANTIC_MEMORY" "1"
_set_env_var "BUTLER_EMBEDDING_PROVIDER" "fastembed"
_set_env_var "BUTLER_EMBEDDING_MODEL" "BAAI/bge-small-en-v1.5"
echo ""

if [[ "$CHECK_ONLY" -eq 0 ]]; then
  echo "Provision complete. Restart gateway after editing API keys if needed."
fi
