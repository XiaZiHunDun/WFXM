#!/usr/bin/env bash
# Sync TODOIST_API_TOKEN from ~/.butler/secrets.yaml into project .env (MCP subprocess reads process env).
#
# Usage:
#   bash scripts/butler-todoist-token-sync.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SECRETS="${BUTLER_SECRETS_PATH:-$HOME/.butler/secrets.yaml}"
ENV_FILE="$ROOT/.env"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -f "$SECRETS" ]]; then
  echo "No secrets file at $SECRETS" >&2
  exit 1
fi

TOKEN="$(python3 - "$SECRETS" <<'PY'
import sys
from pathlib import Path
import yaml
path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
val = str(data.get("TODOIST_API_TOKEN") or "").strip()
if val:
    print(val)
PY
)"

if [[ -z "$TOKEN" ]]; then
  echo "TODOIST_API_TOKEN not found in $SECRETS" >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  cp -a "$ENV_FILE" "${ENV_FILE}.bak.${TS}"
fi

if [[ -f "$ENV_FILE" ]] && grep -q '^TODOIST_API_TOKEN=' "$ENV_FILE"; then
  sed -i "s|^TODOIST_API_TOKEN=.*|TODOIST_API_TOKEN=${TOKEN}|" "$ENV_FILE"
elif [[ -f "$ENV_FILE" ]]; then
  printf '\nTODOIST_API_TOKEN=%s\n' "$TOKEN" >> "$ENV_FILE"
else
  printf 'TODOIST_API_TOKEN=%s\n' "$TOKEN" > "$ENV_FILE"
fi

echo "== .env updated with TODOIST_API_TOKEN (len=${#TOKEN}); backup *.bak.${TS} if any =="
bash "$ROOT/scripts/butler-extension-ext2-preflight.sh"
