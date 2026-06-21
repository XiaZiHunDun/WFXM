#!/usr/bin/env bash
# Rotate TODOIST_API_TOKEN in ~/.butler/secrets.yaml and project .env (same value both places).
#
# Owner steps (Todoist web, this script cannot do):
#   1. https://todoist.com/prefs/integrations → Developer → Revoke old token
#   2. Copy the new API token
#
# Usage (do not pass token on argv — visible in ps):
#   TODOIST_API_TOKEN_NEW='paste-new-token' bash scripts/butler-todoist-token-rotate.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NEW="${TODOIST_API_TOKEN_NEW:-}"
if [[ -z "$NEW" ]]; then
  echo "Set TODOIST_API_TOKEN_NEW to the new Todoist API token (see script header)." >&2
  exit 1
fi
if [[ ${#NEW} -lt 32 ]]; then
  echo "TODOIST_API_TOKEN_NEW looks too short (${#NEW} chars)." >&2
  exit 1
fi

SECRETS="${BUTLER_SECRETS_PATH:-$HOME/.butler/secrets.yaml}"
ENV_FILE="$ROOT/.env"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$(dirname "$SECRETS")"
if [[ -f "$SECRETS" ]]; then
  cp -a "$SECRETS" "${SECRETS}.bak.${TS}"
fi

python3 - "$SECRETS" "$NEW" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
token = sys.argv[2]
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(f'TODOIST_API_TOKEN: "{token}"\n', encoding="utf-8")
PY
chmod 600 "$SECRETS"

if [[ -f "$ENV_FILE" ]]; then
  cp -a "$ENV_FILE" "${ENV_FILE}.bak.${TS}"
  if grep -q '^TODOIST_API_TOKEN=' "$ENV_FILE"; then
    sed -i "s|^TODOIST_API_TOKEN=.*|TODOIST_API_TOKEN=${NEW}|" "$ENV_FILE"
  else
    printf '\nTODOIST_API_TOKEN=%s\n' "$NEW" >> "$ENV_FILE"
  fi
fi

# shellcheck source=scripts/lib/butler-source-env.sh
source "$ROOT/scripts/lib/butler-source-env.sh"
butler_source_env "$ENV_FILE" 2>/dev/null || true
export TODOIST_API_TOKEN="$NEW"
unset TODOIST_API_TOKEN_NEW

echo "== secrets + .env updated (backups *.bak.${TS}) =="
bash "$ROOT/scripts/butler-extension-ext2-preflight.sh"

if [[ -x "$ROOT/scripts/butler-gateway-ops.sh" ]]; then
  echo ""
  echo "== gateway restart =="
  bash "$ROOT/scripts/butler-gateway-ops.sh" restart || true
fi

echo ""
echo "Done. Verify on WeChat: 「用 Todoist 列出所有项目」"
echo "Then revoke the OLD token on Todoist if you have not already."
