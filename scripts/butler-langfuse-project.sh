#!/usr/bin/env bash
# Create ~/.butler/projects/<id>/langfuse.json for a Butler-managed project.
# LangFuse stack itself lives in ~/gongju/langfuse (./ops.sh).
set -euo pipefail

GONGJU_LANGFUSE="${GONGJU_LANGFUSE:-$HOME/gongju/langfuse}"
OPS="$GONGJU_LANGFUSE/ops.sh"

if [[ ! -x "$OPS" ]]; then
  echo "ERROR: $OPS not found. Deploy LangFuse: cd $GONGJU_LANGFUSE && ./ops.sh up" >&2
  exit 1
fi

exec "$OPS" create-project "${1:-}"
