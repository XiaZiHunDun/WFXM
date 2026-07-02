"""P1-C module split — line budgets for core hot paths."""

from __future__ import annotations

import pathlib

import pytest

# SSOT: docs/plans/active/project-optimization-directions-2026-06.md §P1-C
_FILE_BUDGETS: dict[str, int] = {
    "butler/core/llm_retry.py": 160,
    "butler/core/context_compress_pipeline.py": 200,
    "butler/core/context_compress_support.py": 120,
    "butler/core/context_compress_hooks.py": 140,
    "butler/core/tool_batch_finalize.py": 150,
    "butler/core/tool_dispatch.py": 235,
    "butler/core/tool_batch.py": 430,
    "butler/runtime/delegate_job.py": 340,
    "butler/runtime/delegate_job_finalize.py": 130,
    "butler/memory/diagnostics_collect.py": 180,
    "butler/ops/health_report_turn.py": 280,
    "butler/tools/registry_gates.py": 340,
    "butler/session/memory_prefetch_ops.py": 370,
    "butler/permissions/rules_context.py": 170,
    "butler/ops/execution_surface_collect.py": 360,
    "butler/gateway/commands/memory_handlers_ops.py": 200,
    "butler/memory/semantic_project_ops.py": 150,
    "butler/memory/butler_memory_ops.py": 100,
    "butler/memory/semantic_index_ops.py": 200,
    "butler/gateway/outbound_bridge_ops.py": 120,
    "butler/memory/facade_ops.py": 300,
}

_PROCESS_TOOL_CALLS_BUDGET = 150
_COMPRESS_MESSAGES_DELEGATE_BUDGET = 25


@pytest.mark.module_test
@pytest.mark.parametrize("rel_path,max_lines", list(_FILE_BUDGETS.items()))
def test_p1c_module_line_budget(rel_path: str, max_lines: int):
    path = pathlib.Path(rel_path)
    count = sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
    assert count <= max_lines, f"{rel_path} has {count} lines (budget {max_lines})"


@pytest.mark.module_test
def test_process_tool_calls_orchestrator_budget():
    text = pathlib.Path("butler/core/tool_batch.py").read_text(encoding="utf-8")
    start = text.index("def process_tool_calls(")
    end = text.index("\n\nfrom butler.core.tool_batch_finalize", start)
    block = text[start:end]
    lines = block.count("\n") + 1
    assert lines <= _PROCESS_TOOL_CALLS_BUDGET, (
        f"process_tool_calls block is {lines} lines (budget {_PROCESS_TOOL_CALLS_BUDGET})"
    )


@pytest.mark.module_test
def test_compress_messages_delegates_to_pipeline():
    text = pathlib.Path("butler/core/context_compressor.py").read_text(encoding="utf-8")
    start = text.index("def compress_messages(")
    end = text.index("\n", text.index("run_compress_messages", start))
    block = text[start:end]
    lines = block.count("\n") + 1
    assert lines <= _COMPRESS_MESSAGES_DELEGATE_BUDGET
    assert "run_compress_messages" in block
