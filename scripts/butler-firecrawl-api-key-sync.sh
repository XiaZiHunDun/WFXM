#!/usr/bin/env bash
# Sync FIRECRAWL_API_KEY from ~/.butler/secrets.yaml into project .env (MCP subprocess reads process env).
#
# Usage:
#   bash scripts/butler-firecrawl-api-key-sync.sh
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

KEY="$(python3 - "$SECRETS" <<'PY'
import sys
from pathlib import Path
import yaml
path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
val = str(data.get("FIRECRAWL_API_KEY") or "").strip()
if val:
    print(val)
PY
)"

if [[ -z "$KEY" ]]; then
  echo "FIRECRAWL_API_KEY not found in $SECRETS" >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  cp -a "$ENV_FILE" "${ENV_FILE}.bak.${TS}"
fi

if [[ -f "$ENV_FILE" ]] && grep -q '^FIRECRAWL_API_KEY=' "$ENV_FILE"; then
  sed -i "s|^FIRECRAWL_API_KEY=.*|FIRECRAWL_API_KEY=${KEY}|" "$ENV_FILE"
elif [[ -f "$ENV_FILE" ]]; then
  printf '\nFIRECRAWL_API_KEY=%s\n' "$KEY" >> "$ENV_FILE"
else
  printf 'FIRECRAWL_API_KEY=%s\n' "$KEY" > "$ENV_FILE"
fi

echo "== .env updated with FIRECRAWL_API_KEY (len=${#KEY}); backup *.bak.${TS} if any =="
bash "$ROOT/scripts/butler-extension-ext1-preflight.sh"
