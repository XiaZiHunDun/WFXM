"""P0-A exception governance — hotspot ``except Exception`` budgets."""

from __future__ import annotations

import pathlib
import re

import pytest

# SSOT: docs/plans/active/project-optimization-directions-2026-06.md §P0-A
_HOTSPOT_BUDGETS: dict[str, int] = {
    "butler/core/tool_batch.py": 0,
    "butler/core/agent_loop_phases.py": 0,
    "butler/gateway/locked_phases.py": 0,
    "butler/core/agent_loop.py": 0,
    "butler/core/agent_loop_ops.py": 8,
    "butler/gateway/locked_phases_ops.py": 2,
    "butler/memory/facade.py": 0,
    "butler/cli/doctor.py": 0,
    "butler/core/context_compressor.py": 0,
    "butler/gateway/message_pipelines.py": 0,
    "butler/gateway/message_pipelines_fail_closed.py": 4,
    "butler/gateway/inbound_pipeline.py": 0,
    "butler/gateway/inbound_pipeline_ops.py": 1,
    "butler/session/post_session_ops.py": 0,
    "butler/session/post_session_guard.py": 1,
    "butler/ops/health_report_turn.py": 0,
    "butler/core/context_compress_pipeline.py": 0,
    "butler/gateway/handler_helpers.py": 0,
    "butler/runtime/delegate_job.py": 0,
    "butler/runtime/delegate_job_finalize.py": 1,
    "butler/gateway/outbound_bridge.py": 0,
    "butler/memory/diagnostics.py": 0,
    "butler/ops/health_report.py": 0,
    "butler/tools/registry.py": 0,
    "butler/session/memory_prefetch.py": 0,
    "butler/permissions/rules.py": 0,
    "butler/permissions/rules_fail_closed.py": 6,
    "butler/ops/execution_surface_diagnostics.py": 0,
    "butler/gateway/commands/memory_handlers.py": 0,
    "butler/memory/semantic_project.py": 0,
    "butler/memory/butler_memory.py": 0,
    "butler/memory/semantic_index.py": 3,
}

_EXCEPT_RE = re.compile(r"^\s*except\s+Exception\b", re.MULTILINE)


def _count_except_exception(rel_path: str) -> int:
    text = pathlib.Path(rel_path).read_text(encoding="utf-8")
    return len(_EXCEPT_RE.findall(text))


@pytest.mark.module_test
@pytest.mark.parametrize("rel_path,max_allowed", list(_HOTSPOT_BUDGETS.items()))
def test_p0a_hotspot_except_exception_budget(rel_path: str, max_allowed: int):
    count = _count_except_exception(rel_path)
    assert count <= max_allowed, (
        f"{rel_path} has {count} bare `except Exception` (budget {max_allowed}); "
        "use safe_best_effort / _record_skipped_plugin or narrow the exception type"
    )


def test_record_skipped_plugin_emits_best_effort_metric(monkeypatch):
    from butler.core.agent_loop import AgentLoop

    recorded: list[tuple[str, BaseException]] = []

    def _capture(label: str, exc: BaseException) -> None:
        recorded.append((label, exc))

    monkeypatch.setattr(
        "butler.core.best_effort.record_best_effort_skip",
        _capture,
    )
    metrics: list[tuple[str, dict]] = []

    def _inc(name: str, *, labels: dict | None = None) -> None:
        metrics.append((name, labels or {}))

    monkeypatch.setattr("butler.ops.runtime_metrics.inc", _inc)

    loop = AgentLoop.__new__(AgentLoop)
    loop.diagnostics = {}
    loop._record_skipped_plugin("test_plugin", RuntimeError("boom"))

    assert recorded[0][0] == "agent_loop.test_plugin"
    assert isinstance(recorded[0][1], RuntimeError)
    assert str(recorded[0][1]) == "boom"
    assert metrics == [("best_effort_skip", {"path": "agent_loop.test_plugin"})]
    assert loop.diagnostics["skipped"][0]["plugin"] == "test_plugin"
