#!/usr/bin/env bash
# Sync GITHUB_TOKEN from ~/.butler/secrets.yaml into project .env (MCP subprocess reads process env).
#
# Usage:
#   bash scripts/butler-github-token-sync.sh
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
for key in ("GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"):
    val = str(data.get(key) or "").strip()
    if val:
        print(val)
        break
PY
)"

if [[ -z "$TOKEN" ]]; then
  echo "GITHUB_TOKEN not found in $SECRETS" >&2
  exit 1
fi

mkdir -p "$(dirname "$SECRETS")"
if [[ -f "$ENV_FILE" ]]; then
  cp -a "$ENV_FILE" "${ENV_FILE}.bak.${TS}"
fi

if [[ -f "$ENV_FILE" ]] && grep -q '^GITHUB_TOKEN=' "$ENV_FILE"; then
  sed -i "s|^GITHUB_TOKEN=.*|GITHUB_TOKEN=${TOKEN}|" "$ENV_FILE"
elif [[ -f "$ENV_FILE" ]]; then
  printf '\nGITHUB_TOKEN=%s\n' "$TOKEN" >> "$ENV_FILE"
else
  printf 'GITHUB_TOKEN=%s\n' "$TOKEN" > "$ENV_FILE"
fi

echo "== .env updated with GITHUB_TOKEN (len=${#TOKEN}); backup *.bak.${TS} if any =="
bash "$ROOT/scripts/butler-extension-ext4-preflight.sh"
