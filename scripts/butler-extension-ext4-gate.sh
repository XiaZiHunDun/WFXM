#!/usr/bin/env bash
# PROD-P2-04 / EXT-4 gate: GitHub OpenAPI MCP manifest + spec + grounding (no live token).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT}:$ROOT"

echo "=== EXT-4 GitHub OpenAPI gate ==="
python3 -m pytest \
  tests/test_github_openapi_ext4.py \
  tests/test_extension_manifest.py \
  tests/test_github_grounding.py \
  tests/test_extension_verify.py \
  tests/test_secrets_contract.py::test_extension_manifests_included \
  tests/test_secrets_contract.py::test_github_manifest_secret_contract_shape \
  -q --tb=line
echo "EXT-4 GATE: PASS"
