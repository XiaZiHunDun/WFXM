"""Tests for butler.workflow_step_runner (ENG-4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from butler.task_orchestrator import AgentResult, AgentSpawnConfig, TaskNode
from butler.workflow_step_runner import run_rescue_steps, run_step_with_retry


@pytest.mark.asyncio
async def test_run_step_with_retry_success_first_attempt():
    node = TaskNode(
        id="a",
        config=AgentSpawnConfig(role="dev", task="do it"),
        max_retries=2,
    )
    ok = AgentResult(success=True, response="done")
    spawn = AsyncMock(return_value=ok)
    out = await run_step_with_retry(node, spawn=spawn, on_progress=None)
    assert out.success is True
    spawn.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_rescue_steps_merges_output():
    from butler.core.workflow_flags import workflow_rescue_enabled

    assert workflow_rescue_enabled()
    node = TaskNode(
        id="main",
        config=AgentSpawnConfig(role="dev", task="fail"),
        rescue_configs=[AgentSpawnConfig(role="dev", task="rescue")],
    )
    failed = AgentResult(success=False, error="boom", response="partial")
    spawn = AsyncMock(return_value=AgentResult(success=True, response="rescue out"))
    out = await run_rescue_steps(node, failed, spawn=spawn)
    assert out.success is False
    assert "rescue out" in (out.response or "")
    spawn.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_step_with_retry_invokes_rescue_on_failure():
    node = TaskNode(
        id="main",
        config=AgentSpawnConfig(role="dev", task="fail"),
        max_retries=1,
        rescue_configs=[AgentSpawnConfig(role="dev", task="rescue")],
    )
    fail = AgentResult(success=False, error="primary")
    rescue = AgentResult(success=True, response="rescued")

    async def _spawn(cfg, **kwargs):
        if "rescue" in (cfg.task or ""):
            return rescue
        return fail

    out = await run_step_with_retry(node, spawn=_spawn)
    assert "rescued" in (out.response or "")
