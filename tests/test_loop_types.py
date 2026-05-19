"""Tests for AgentLoop public type re-exports."""

from butler.core.agent_loop import LoopConfig as ReExportedLoopConfig
from butler.core.agent_loop import LoopResult as ReExportedLoopResult
from butler.core.agent_loop import LoopStatus as ReExportedLoopStatus
from butler.core.loop_types import LoopConfig, LoopResult, LoopStatus


def test_loop_types_are_reexported_from_agent_loop():
    assert ReExportedLoopStatus is LoopStatus
    assert ReExportedLoopConfig is LoopConfig
    assert ReExportedLoopResult is LoopResult


def test_loop_result_has_default_diagnostics():
    result = LoopResult(status=LoopStatus.COMPLETED)

    assert result.diagnostics == {}
