#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Only real source test files in packages/ apps/ tests/ ; skip node_modules and tsbuildinfo dirs.
find packages apps tests \
  \( -name node_modules -o -name .turbo -o -name dist \) -prune -o \
  -type f -name "*.test.ts" -print \
  | sort -u
