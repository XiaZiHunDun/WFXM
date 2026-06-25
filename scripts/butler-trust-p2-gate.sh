#!/usr/bin/env bash
# PROD-P2-03 trust patch batch gate (PII / secrets Fernet / MCP SSRF).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT}:$ROOT"

echo "=== PROD-P2-03 trust batch gate ==="
python3 -m pytest \
  tests/test_trust_p2_batch.py \
  tests/test_mcp_features.py::test_http_metadata_ip_blocked_even_with_hosts_allow \
  tests/test_phase_b_external.py::test_pii_scrub_private_ipv4 \
  tests/test_install_scan_ssrf.py \
  tests/test_deferred_external.py::test_secrets_yaml_roundtrip \
  -q --tb=line
echo "TRUST P2-03 GATE: PASS"
