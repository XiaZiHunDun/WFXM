"""Shared fixtures for conversational (live-LLM) tests.

Gate: BUTLER_RUN_REAL_API_SMOKE=1 + MINIMAX_API_KEY must be set.
All tests carry the ``live_llm`` and ``conversational`` markers so
default pytest runs (``-m 'not live_llm'``) skip them automatically.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest -m conversational tests/conversational/ -v --timeout=120
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Generator
from unittest.mock import patch

import pytest
import yaml

from butler.config import ModelConfig, get_butler_settings, reload_butler_settings
from butler.gateway.message_handler import ButlerMessageHandler
from butler.project.manager import ProjectManager
from butler.tools.registry import (
    get_tool_audit_events,
    reset_tool_audit_events,
)
from butler.transport.providers import get_provider

from tests.conversational.evaluation import (
    ConversationRubric,
    TurnResult,
    evaluate_turn,
)


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------

def _require_smoke_enabled() -> None:
    if os.getenv("BUTLER_RUN_REAL_API_SMOKE") != "1":
        pytest.skip("set BUTLER_RUN_REAL_API_SMOKE=1 to run conversational tests")


def _require_minimax() -> None:
    _require_smoke_enabled()
    profile = get_provider("minimax")
    if profile is None:
        pytest.skip("minimax provider profile missing")
    if not profile.resolve_api_key():
        pytest.skip(f"set one of {profile.env_vars} for conversational tests")
    reload_butler_settings()
    settings = get_butler_settings()
    mc = settings.get_model_config("butler")
    provider = (mc.provider or settings.default_provider or "minimax").strip().lower()
    if provider != "minimax":
        pytest.skip(f"butler role is {provider}, need minimax for conversational tests")
    model_override = os.getenv("BUTLER_SMOKE_MINIMAX_MODEL", "").strip()
    if model_override:
        settings.set_runtime_model_override(
            "butler", ModelConfig(provider="minimax", model=model_override)
        )


def _reset_singletons() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


# ---------------------------------------------------------------------------
# Environment setup helpers
# ---------------------------------------------------------------------------

def _enable_daily_modules(monkeypatch) -> None:
    """Ensure memo / contacts / expense / habits modules are enabled."""
    for var in (
        "BUTLER_MEMO_ENABLED",
        "BUTLER_CONTACTS_ENABLED",
        "BUTLER_EXPENSE_ENABLED",
        "BUTLER_HABITS_ENABLED",
    ):
        monkeypatch.setenv(var, "1")


def _setup_empty_projects(tmp_path: Path, monkeypatch) -> Path:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    _reset_singletons()
    return projects_dir


def _setup_lingwen_project(tmp_path: Path, monkeypatch) -> Path:
    """Create a minimal LingWen1 project stub for dev scenario tests."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(exist_ok=True)
    proj = projects_dir / "LingWen1"
    proj.mkdir(exist_ok=True)
    (proj / "docs").mkdir(exist_ok=True)
    (proj / "README.md").write_text(
        "# 灵文1号\n小说工厂试点项目\nCONV_TEST_MARKER\n",
        encoding="utf-8",
    )

    spec = {
        "name": "灵文1号",
        "type": "content",
        "description": "小说工厂试点（拟人对话测试环境）",
        "status": "active",
        "workspace": str(proj),
        "lead": True,
        "tools": [
            "read_file", "write_file", "delete_file", "patch",
            "search_files", "terminal", "list_directory",
        ],
        "dev": {
            "test_command": "echo 'all tests passed'",
            "build_command": "echo 'build ok'",
            "main_branch": "main",
        },
    }
    (proj / "project.yaml").write_text(
        yaml.safe_dump(spec, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("BUTLER_ENABLE_GIT", "1")
    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    _reset_singletons()
    return proj


# ---------------------------------------------------------------------------
# Conversational turn runner
# ---------------------------------------------------------------------------

def send_message(
    handler: ButlerMessageHandler,
    text: str,
    *,
    session_key: str = "wechat:conv-test",
    platform: str = "wechat",
    rubric: ConversationRubric | None = None,
) -> TurnResult:
    """Send one message through the handler, capture timing + tool audit."""
    # Reset ALL events (session key inside handler may differ from the one we pass)
    reset_tool_audit_events()

    t0 = time.monotonic()
    with patch("butler.session.lifecycle.sync_turn_memory", return_value={}):
        response = handler.handle_message(
            text, session_key=session_key, platform=platform,
        )
    latency = time.monotonic() - t0

    # Capture all events — the internal session key may include project suffix
    tool_events = list(get_tool_audit_events())

    result = TurnResult(
        user_input=text,
        response=response or "",
        latency_seconds=latency,
        tool_events=tool_events,
    )

    if rubric:
        evaluate_turn(result, rubric)

    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def live_minimax_handler(tmp_butler_home, tmp_path, monkeypatch):
    """ButlerMessageHandler wired to real MiniMax, no projects, daily modules on."""
    _require_minimax()
    _enable_daily_modules(monkeypatch)
    _setup_empty_projects(tmp_path, monkeypatch)
    handler = ButlerMessageHandler(channel="gateway")
    return handler


@pytest.fixture
def lingwen_handler(tmp_butler_home, tmp_path, monkeypatch):
    """ButlerMessageHandler wired to real MiniMax with LingWen1 project active."""
    _require_minimax()
    _enable_daily_modules(monkeypatch)
    _setup_lingwen_project(tmp_path, monkeypatch)
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat", chat_id="conv-dev", name="灵文1号",
    )
    return handler
