#!/usr/bin/env bash
# Verify bubblewrap (bwrap) before starting v5 with BUTLER_V5_SANDBOX=bubblewrap.
# Exit 0 when bwrap responds; exit 1 otherwise (systemd ExecStartPre fail-closed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
pnpm exec tsx cli/src/index.ts sandbox-preflight
