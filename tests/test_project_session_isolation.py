"""Sprint 1: per-project session isolation (platform:chat_id:project)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.core.agent_loop import LoopResult, LoopStatus
from butler.gateway.message_handler import ButlerMessageHandler
from butler.project_manager import ProjectManager
from butler.session_keys import build_session_key

LLM_PATCH = "butler.transport.llm_client.LLMClient"


def _reset_singletons() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


def _setup_two_projects(tmp_path: Path, monkeypatch) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    for name, desc in (("alpha", "Project Alpha"), ("beta", "Project Beta")):
        proj = projects_dir / name
        proj.mkdir()
        (proj / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": name,
                    "type": "software",
                    "description": desc,
                    "workspace": str(proj),
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    _reset_singletons()


def _text_response(content: str):
    from butler.transport.types import NormalizedResponse, Usage

    return NormalizedResponse(
        content=content,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.fixture
def patch_llm(mock_llm_response):
    with (
        patch(f"{LLM_PATCH}.complete") as mock_complete,
        patch(f"{LLM_PATCH}.stream") as mock_stream,
    ):
        default = mock_llm_response()
        mock_complete.return_value = default
        mock_stream.return_value = default
        yield mock_complete, mock_stream


@pytest.mark.integration
class TestProjectSessionIsolation:
    def test_session_keys_include_project(self):
        assert build_session_key(platform="wechat", chat_id="u1", project="灵文") == "wechat:u1:灵文"
        assert build_session_key(platform="wechat", chat_id="u1", project="") == "wechat:u1:_"

    def test_switch_rebuilds_loops_per_project(self, tmp_path, monkeypatch, patch_llm):
        _setup_two_projects(tmp_path, monkeypatch)
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response("ok")
        mock_stream.return_value = mock_complete.return_value

        handler = ButlerMessageHandler(channel="gateway")
        handler._orchestrator.project_manager.switch_project("alpha")

        handler.handle_message("在 alpha 说话", platform="wechat", external_id="user1")
        sk_alpha = build_session_key(platform="wechat", chat_id="user1", project="alpha")
        loop_alpha = handler._sessions[sk_alpha]

        handler._handle_command("/switch beta", session_key=sk_alpha)
        assert sk_alpha not in handler._sessions

        handler.handle_message("在 beta 说话", platform="wechat", external_id="user1")
        sk_beta = build_session_key(platform="wechat", chat_id="user1", project="beta")
        loop_beta = handler._sessions[sk_beta]

        assert loop_alpha is not loop_beta

        handler._handle_command("/switch alpha", session_key=sk_beta)
        handler.handle_message("回到 alpha", platform="wechat", external_id="user1")
        assert handler._sessions[sk_alpha] is not loop_alpha

    def test_switch_resets_all_sessions_for_chat(self, tmp_path, monkeypatch):
        _setup_two_projects(tmp_path, monkeypatch)
        handler = ButlerMessageHandler(channel="gateway")
        handler._orchestrator.project_manager.switch_project("alpha")

        sk_alpha = build_session_key(platform="wechat", chat_id="u1", project="alpha")
        loop_alpha = MagicMock(messages=[{"role": "user", "content": "alpha-only"}])
        handler._sessions[sk_alpha] = loop_alpha
        handler._session_registry.touch(sk_alpha)

        handler._handle_command("/switch beta", session_key=sk_alpha)

        assert sk_alpha not in handler._sessions
