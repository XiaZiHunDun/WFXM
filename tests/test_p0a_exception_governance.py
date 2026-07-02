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
    "butler/core/agent_loop_ops.py": 2,
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
    "butler/permissions/rules_fail_closed.py": 0,
    "butler/permissions/rules_fail_closed_ops.py": 6,
    "butler/ops/execution_surface_diagnostics.py": 0,
    "butler/gateway/commands/memory_handlers.py": 0,
    "butler/memory/semantic_project.py": 0,
    "butler/memory/butler_memory.py": 0,
    "butler/memory/semantic_index.py": 0,
    "butler/memory/semantic_index_ops.py": 3,
    "butler/ops/rag_diagnostics.py": 0,
    "butler/ops/rag_diagnostics_ops.py": 0,
    "butler/memory/vector_store.py": 0,
    "butler/memory/vector_store_ops.py": 4,
    "butler/core/session_transcript.py": 0,
    "butler/core/session_transcript_ops.py": 0,
    "butler/tools/registry_gates.py": 0,
    "butler/tools/registry_invoke_ops.py": 1,
    "butler/ops/registry_diagnostics.py": 0,
    "butler/ops/registry_diagnostics_ops.py": 0,
    "butler/mcp/registry_hook.py": 0,
    "butler/mcp/registry_hook_ops.py": 1,
    "butler/gateway/commands/registry_handlers.py": 0,
    "butler/gateway/commands/registry_handlers_ops.py": 1,
    "butler/tools/registry_tools.py": 0,
    "butler/tools/registry_tools_ops.py": 1,
    "butler/gateway/commands/info_commands.py": 0,
    "butler/gateway/commands/info_commands_ops.py": 0,
    "butler/core/transcript_export.py": 0,
    "butler/core/transcript_export_ops.py": 0,
    "butler/core/transcript_search.py": 0,
    "butler/core/transcript_search_ops.py": 0,
    "butler/ops/embedding_diagnostics.py": 0,
    "butler/ops/embedding_diagnostics_ops.py": 0,
    "butler/ops/observation_diagnostics.py": 0,
    "butler/ops/observation_diagnostics_ops.py": 0,
    "butler/gateway/commands/help_handlers.py": 0,
    "butler/gateway/commands/help_handlers_ops.py": 0,
    "butler/tools/memory_tools.py": 0,
    "butler/tools/memory_tools_ops.py": 0,
    "butler/gateway/gateway_transcript.py": 0,
    "butler/gateway/gateway_transcript_ops.py": 0,
    "butler/gateway/command_registry.py": 0,
    "butler/gateway/command_registry_ops.py": 1,
    "butler/session/post_session.py": 0,
    "butler/session/post_session_extract_ops.py": 3,
    "butler/gateway/message_handler.py": 0,
    "butler/gateway/message_handler_ops.py": 1,
    "butler/gateway/turn_post_pipeline.py": 0,
    "butler/gateway/turn_post_pipeline_ops.py": 1,
    "butler/ops/degradation_registry.py": 0,
    "butler/ops/degradation_registry_ops.py": 0,
    "butler/gateway/hooks.py": 0,
    "butler/gateway/hooks_ops.py": 3,
    "butler/hooks/runner.py": 0,
    "butler/hooks/runner_ops.py": 1,
    "butler/core/context_pipeline.py": 0,
    "butler/core/context_pipeline_ops.py": 1,
    "butler/memory/coding_recall.py": 0,
    "butler/memory/transcript_recall.py": 0,
    "butler/memory/unified_recall.py": 0,
    "butler/memory/observation_recall.py": 0,
    "butler/memory/retrieval_telemetry.py": 0,
    "butler/memory/recall_ops.py": 0,
    "butler/memory/retrieval_telemetry_ops.py": 0,
    "butler/core/pim_state.py": 0,
    "butler/core/pim_state_ops.py": 0,
    "butler/tool_guardrails.py": 0,
    "butler/tool_guardrails_ops.py": 0,
    "butler/memory/embedding.py": 0,
    "butler/memory/embedding_ops.py": 2,
    "butler/tools/delegate_report.py": 0,
    "butler/tools/delegate_report_ops.py": 0,
    "butler/extensions/opencode.py": 0,
    "butler/extensions/opencode_ops.py": 2,
    "butler/tools/builtin_register.py": 0,
    "butler/tools/builtin_register_ops.py": 0,
    "butler/memory/facade_ops.py": 1,
    "butler/skills/router.py": 0,
    "butler/skills/router_ops.py": 0,
    "butler/cli/skills_registry.py": 0,
    "butler/cli/skills_registry_ops.py": 1,
    "butler/cli/memory_cli.py": 0,
    "butler/cli/memory_cli_ops.py": 0,
    "butler/core/tool_dispatch.py": 0,
    "butler/core/tool_dispatch_ops.py": 0,
    "butler/skills/learn.py": 0,
    "butler/skills/learn_ops.py": 2,
    "butler/skills/write_approval.py": 0,
    "butler/skills/write_approval_ops.py": 1,
    "butler/ops/onboard.py": 0,
    "butler/ops/onboard_ops.py": 0,
    "butler/memory_settings.py": 0,
    "butler/memory_settings_ops.py": 0,
    "butler/core/tool_dispatch_doom.py": 0,
    "butler/core/tool_dispatch_doom_ops.py": 1,
    "butler/ops/owner_pmf_metrics.py": 0,
    "butler/ops/owner_pmf_metrics_ops.py": 0,
    "butler/ops/owner_feedback.py": 0,
    "butler/ops/owner_feedback_ops.py": 0,
    "butler/core/schema_recovery.py": 0,
    "butler/core/schema_recovery_ops.py": 0,
    "butler/skills/manager.py": 0,
    "butler/skills/manager_ops.py": 0,
    "butler/core/best_effort.py": 3,
    "butler/core/events_sink.py": 0,
    "butler/core/events_sink_ops.py": 0,
    "butler/core/dev_state_context_adapter.py": 0,
    "butler/core/dev_state_context_adapter_ops.py": 1,
    "butler/core/llm_retry.py": 1,
    "butler/core/llm_retry_ops.py": 0,
    "butler/core/tool_batch_finalize.py": 0,
    "butler/core/tool_batch_finalize_ops.py": 1,
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
