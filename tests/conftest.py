"""Shared test fixtures for Butler v4 test suite."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# Gateway corpus L1 fixtures (must be registered from top-level conftest)
pytest_plugins = ["tests.corpus.conftest_gateway"]


@pytest.fixture(autouse=True)
def _isolate_butler_home(tmp_path, monkeypatch):
    """Every test gets its own BUTLER_HOME so nothing leaks."""
    home = tmp_path / ".butler"
    home.mkdir()
    monkeypatch.setenv("BUTLER_HOME", str(home))
    monkeypatch.setenv("BUTLER_READ_BEFORE_EDIT", "0")
    return home


@pytest.fixture
def tmp_butler_home(_isolate_butler_home):
    """Explicit access to the isolated BUTLER_HOME directory."""
    return _isolate_butler_home


@pytest.fixture
def mock_llm_response():
    """Factory: create a NormalizedResponse with defaults."""
    from butler.transport.types import NormalizedResponse, Usage

    def _factory(
        content: str | None = "hello",
        tool_calls=None,
        finish_reason: str = "stop",
        reasoning: str | None = None,
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
    ):
        return NormalizedResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            reasoning=reasoning,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    return _factory


def link_llm_stream_mock(mock_complete, mock_stream) -> None:
    """Route LLMClient.stream() through complete() so side_effect lists advance in order."""
    mock_stream.side_effect = lambda *args, **kwargs: mock_complete(*args, **kwargs)


@pytest.fixture
def mock_llm_client(mock_llm_response):
    """LLMClient with mocked complete/stream methods."""
    from butler.transport.llm_client import LLMClient

    client = LLMClient(provider="minimax", model="test-model")
    client.complete = MagicMock(return_value=mock_llm_response())
    client.stream = MagicMock(return_value=mock_llm_response())
    return client


@pytest.fixture
def sample_agent_loop(mock_llm_client):
    """AgentLoop pre-wired with mock client and real tools."""
    from butler.core.agent_loop import AgentLoop, LoopConfig
    from butler.tools.registry import get_tool_definitions, dispatch_tool

    return AgentLoop(
        client=mock_llm_client,
        system_prompt="You are a test assistant.",
        tools=get_tool_definitions(),
        tool_dispatcher=dispatch_tool,
        config=LoopConfig(stream=False),
    )


@pytest.fixture
def butler_orchestrator(tmp_butler_home, monkeypatch):
    """Isolated ButlerOrchestrator instance.

    Sprint 17 SEC-11 owner-gate completion: 多数 slash 命令的 registry handler
    现在有 owner gate. e2e 测试不验证 owner gate (有 test_sprint11_sec* 专门
    覆盖), 走 BUTLER_PROJECT_CREATE_OPEN=1 dev 旁路, 避免每个测试都伪造
    owner 身份. tmp_butler_home 来自上游 fixture.
    """
    monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
    from butler.orchestrator import ButlerOrchestrator

    return ButlerOrchestrator(user_id="test_user", channel="test")


@pytest.fixture
def sample_project_dir(tmp_path):
    """Temp directory with a minimal project.yaml."""
    proj_dir = tmp_path / "test-project"
    proj_dir.mkdir()
    yaml_content = (
        "name: test-project\n"
        "type: software\n"
        "description: A test project\n"
        "workspace: {workspace}\n"
    ).format(workspace=str(proj_dir))
    (proj_dir / "project.yaml").write_text(yaml_content, encoding="utf-8")
    return proj_dir


@pytest.fixture
def sample_report():
    """Standard AgentReport for testing."""
    from butler.report import AgentReport, Change

    return AgentReport(
        headline="Test operation completed",
        changes=[
            Change(file="main.py", action="modified", description="Updated logic"),
            Change(file="utils.py", action="created", description="New helper"),
        ],
        decisions=["Used dataclass over dict"],
        issues=["Needs unit tests"],
        summary="Successfully completed test operation",
        success=True,
        iterations=3,
        tool_calls=5,
        tokens_used=1500,
        elapsed_seconds=8.2,
    )
