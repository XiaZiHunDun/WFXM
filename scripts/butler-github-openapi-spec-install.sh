#!/usr/bin/env bash
# Install pinned GitHub readonly OpenAPI spec to ~/.butler/openapi/
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/.butler/openapi/github-readonly.yml"
DEST="${BUTLER_OPENAPI_DIR:-$HOME/.butler/openapi}/github-readonly.yml"
mkdir -p "$(dirname "$DEST")"
cp "$SRC" "$DEST"
echo "Installed: $DEST"
