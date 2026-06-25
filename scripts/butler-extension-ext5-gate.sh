#!/usr/bin/env bash
# EXT-5 gate: manifest + ingest contract (no live markitdown-mcp).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT}:$ROOT"

echo "=== EXT-5 MarkItDown MCP gate ==="
python3 -m pytest \
  tests/test_markitdown_ext5.py \
  tests/test_extension_manifest.py::test_load_all_manifests_non_empty \
  -q --tb=line
echo "EXT-5 GATE: PASS"
