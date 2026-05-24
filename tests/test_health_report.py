"""Unit tests for butler.ops.health_report."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from butler.ops.health_report import HealthReportInput, build_health_report


def test_build_health_report_static_branch():
    orch = MagicMock()
    orch._settings = MagicMock()
    orch.project_manager.get_current.return_value = None

    with (
        patch(
            "butler.memory.diagnostics.format_memory_diagnostic_lines",
            return_value=["记忆分层: test"],
        ),
        patch(
            "butler.runtime.diagnostics.format_runtime_diagnostic_lines",
            return_value=["runtime: ok"],
        ),
        patch(
            "butler.model_resolve.format_model_diagnostic_lines",
            return_value=["--- 有效模型 ---"],
        ),
        patch(
            "butler.ops.snapshot.format_ops_diagnostic_lines",
            return_value=["ops: ok"],
        ),
    ):
        text = build_health_report(
            HealthReportInput(
                session_key="sess-a",
                health=None,
                tool_summary={"total": 0, "failed": 0, "codes": []},
                mem_stats={"project_name": ""},
                orchestrator=orch,
            )
        )

    assert text.startswith("Butler 诊断\n会话: sess-a")
    assert "上下文用量" in text
    assert "轮次诊断: 暂无" in text
    assert "记忆分层: test" in text
    assert "工具调用:" not in text


def test_build_health_report_turn_and_tools():
    orch = MagicMock()
    orch._settings = MagicMock()
    orch.project_manager.get_current.return_value = None

    with (
        patch("butler.memory.diagnostics.format_memory_diagnostic_lines", return_value=[]),
        patch("butler.runtime.diagnostics.format_runtime_diagnostic_lines", return_value=[]),
        patch("butler.model_resolve.format_model_diagnostic_lines", return_value=[]),
        patch("butler.ops.snapshot.format_ops_diagnostic_lines", return_value=[]),
        patch(
            "butler.transport.auxiliary_client.resolve_auxiliary_config",
            side_effect=RuntimeError("no aux"),
        ),
    ):
        text = build_health_report(
            HealthReportInput(
                session_key="default",
                health={
                    "session_key": "default",
                    "platform": "wechat",
                    "hygiene_compressed": True,
                    "context_estimated_tokens": 50000,
                    "context_max_tokens": 128000,
                    "context_usage_percent": 39.1,
                    "context_tier_label": "正常",
                    "skill_context_injected": False,
                    "memory_context_injected": True,
                    "memory_sync": {"skipped": True},
                },
                tool_summary={"total": 2, "failed": 1, "codes": ["X"]},
                mem_stats={},
                orchestrator=orch,
            )
        )

    assert "压缩: 是" in text
    assert "上下文用量:" in text
    assert "记忆提炼模型(post_session): 未配置" in text
    assert "工具调用: 2" in text
    assert "工具错误码: X" in text
