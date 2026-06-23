"""Shared fixtures for gateway corpus runners (L1 utterance + multiturn + variants)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from butler.gateway.message_handler import ButlerMessageHandler
from tests.corpus.harness.gateway_scripts import pad_script
from tests.gateway.test_gateway_acceptance import LLM_PATCH, _text_response
from tests.gateway.test_gateway_dev_conversations import (
    HELLO_CONTENT,
    HELLO_REL,
    _bind_llm_script,
    _delegate_create_hello_script,
    _setup_dual_gateway_projects,
    _setup_lingwen_gateway_project,
)


def resolved_session_key(handler: ButlerMessageHandler, entry: dict) -> str:
    raw = entry.get("session_key") or "wechat:u1"
    chat_id = "u1"
    if raw.startswith("wechat:"):
        parts = raw.split(":")
        if len(parts) > 1 and parts[1]:
            chat_id = parts[1]
    return handler.resolve_session_key(
        session_key=raw,
        platform="wechat",
        external_id=chat_id,
    )


def catalog_message_kwargs(
    session_key: str,
    *,
    platform: str = "wechat",
    external_id: str | None = None,
) -> dict[str, str]:
    """Match real gateway inbound: always pass external_id so session keys stay canonical."""
    from butler.session.keys import chat_id_from_session_key

    chat_id = str(external_id or chat_id_from_session_key(session_key) or "default").strip()
    return {
        "session_key": session_key,
        "platform": platform,
        "external_id": chat_id or "default",
    }


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


@pytest.fixture
def catalog_handlers(tmp_path, monkeypatch, tmp_butler_home):
    import yaml as _yaml
    from butler.report import clear_report_cache
    from tests.gateway.test_gateway_handler import _reset_singletons

    clear_report_cache()
    _setup_dual_gateway_projects(tmp_path, monkeypatch)
    lw_proj = _setup_lingwen_gateway_project(tmp_path, monkeypatch)
    spec_path = lw_proj / "project.yaml"
    spec = _yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec["workflows"] = [{"name": "novel-factory", "description": "demo wf"}]
    spec_path.write_text(
        _yaml.safe_dump(spec, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "u1")
    monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "0")
    monkeypatch.setenv("BUTLER_DEV_AUTO_VERIFY", "0")
    _reset_singletons()

    dual = ButlerMessageHandler(channel="gateway")
    dual._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat",
        chat_id="u1",
        name="灵文1号",
    )

    lingwen = ButlerMessageHandler(channel="gateway")
    lingwen._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat",
        chat_id="u1",
        name="灵文1号",
    )

    lingwen_wf = ButlerMessageHandler(channel="gateway")
    lingwen_wf._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat",
        chat_id="u1",
        name="灵文1号",
    )
    wf_state = lw_proj / "novel-factory" / "workflow_state.json"
    wf_state.parent.mkdir(parents=True, exist_ok=True)
    wf_state.write_text('{"phase": "draft", "step": "outline"}\n', encoding="utf-8")

    helpers = {
        "HELLO_REL": HELLO_REL,
        "HELLO_CONTENT": HELLO_CONTENT,
        "delegate_create_hello_script": _delegate_create_hello_script,
        "bind_script": None,
    }

    return {
        "dual": (dual, lw_proj),
        "lingwen": (lingwen, lw_proj),
        "lingwen_workflow": (lingwen_wf, lw_proj),
        "helpers": helpers,
    }


def extended_catalog_setup(
    entry: dict,
    *,
    handler: ButlerMessageHandler,
    proj: Path,
    helpers: dict,
    patch_llm,
) -> str:
    """Session setup hooks shared by utterance + multiturn runners."""
    from tests.corpus.harness.gateway_catalog import apply_catalog_setup

    setup = entry.get("setup")
    sk = resolved_session_key(handler, entry)
    mock_complete, mock_stream = patch_llm
    helpers_with_bind = {
        **helpers,
        "bind_script": lambda script: _bind_llm_script(
            mock_complete, mock_stream, pad_script(script)
        ),
    }

    if setup == "prior_chat_turn":
        _bind_llm_script(mock_complete, mock_stream, [_text_response("好的，已读取 README。")])
        handler.handle_message("请先读 README", **catalog_message_kwargs(sk))
        return sk

    if setup == "prior_chat_then_new":
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [_text_response("已读完 wechat-smoke 文件。")],
        )
        handler.handle_message("请读取 wechat-smoke", **catalog_message_kwargs(sk))
        handler.handle_message("/新对话", **catalog_message_kwargs(sk))
        return sk

    apply_catalog_setup(
        entry,
        handler=handler,
        proj=proj,
        session_key=sk,
        helpers=helpers_with_bind,
    )
    # Re-resolve after setup hooks (e.g. /切换) so audit/tool lookups use the active project.
    return resolved_session_key(handler, entry)
