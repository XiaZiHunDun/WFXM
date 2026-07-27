#!/usr/bin/env bash
# D3-6 experience mining smoke gate
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

echo "=== D3-6 experience mining ==="
python -m pytest tests/test_experience_mining_d36.py tests/test_experience_mining_builtin.py tests/test_phase4_quality.py::TestExperienceMining -q

echo "=== coding knowledge premise (CA3/CT3) ==="
python -m pytest tests/test_premise_coding_knowledge.py -k "Experience or CT3" -q

echo "=== CLI mine (temp workspace) ==="
TMP=$(mktemp -d)
echo '[project]\nname="smoke"' > "$TMP/pyproject.toml"
python -m butler.memory.experience_mining_cli mine --workspace "$TMP" --json | head -n 20

echo "OK: D3-6 experience mining gates passed"
