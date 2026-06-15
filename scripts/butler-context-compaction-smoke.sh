#!/usr/bin/env bash
# Context + memory compaction smoke (layer A/B + S_f diagnostics).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."

PY="${PYTHONPATH:+}${PYTHONPATH:+.}python3"
if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
  PY=/home/ailearn/miniconda3/bin/python3
fi

echo "== context / compaction pytest subset =="
"$PY" -m pytest \
  tests/test_compaction_memory_diag.py \
  tests/test_turn_compaction.py \
  tests/test_preemptive_compact.py \
  tests/test_post_compact_agents_sections.py \
  tests/test_fact_extraction.py \
  tests/test_context_pipeline.py \
  tests/test_phase1_observability.py \
  tests/test_memory_metrics_benchmark.py::TestMemoryBenchmark::test_mb6_fact_compaction \
  -q --tb=line

echo ""
echo "Context compaction smoke: PASSED"
echo "真机长会话剧本: docs/guides/context-compaction-smoke-checklist.md"
