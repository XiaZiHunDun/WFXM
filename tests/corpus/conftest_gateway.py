"""Shared fixtures for gateway corpus runners (L1 utterance + multiturn + variants)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from butler.gateway.message_handler import ButlerMessageHandler
from butler.report import AgentReport, Change, cache_report, clear_report_cache
from tests.corpus.harness.gateway_scripts import pad_script
from tests.test_gateway_acceptance import LLM_PATCH, _text_response
from tests.test_gateway_dev_conversations import (
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
    from tests.test_gateway_handler import _reset_singletons

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

    if setup == "prior_chat_turn":
        _bind_llm_script(mock_complete, mock_stream, [_text_response("好的，已读取 README。")])
        handler.handle_message("请先读 README", session_key=sk, platform="wechat")
        return sk

    if setup == "cached_report_smoke_write":
        clear_report_cache(sk)
        cache_report(
            AgentReport(
                headline="内容代理已完成任务",
                task_preview="写 docs/wechat-smoke.md",
                summary="已写入 wechat-smoke.md",
                changes=[Change("docs/wechat-smoke.md", "created", "微信验收")],
                success=True,
            ),
            session_key=sk,
        )
        return sk

    if setup == "prior_chat_then_new":
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [_text_response("已读完 wechat-smoke 文件。")],
        )
        handler.handle_message("请读取 wechat-smoke", session_key=sk, platform="wechat")
        handler.handle_message("/新对话", session_key=sk, platform="wechat")
        return sk

    if setup == "cached_report_multi_changes":
        clear_report_cache(sk)
        cache_report(
            AgentReport(
                headline="开发代理已完成任务",
                summary="完整摘要",
                changes=[
                    Change("docs/a.md", "created", ""),
                    Change("docs/b.md", "modified", ""),
                ],
                success=True,
            ),
            session_key=sk,
        )
        return sk

    if setup == "patch_target_file":
        rel = "docs/patch-target.txt"
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text("OLD\n", encoding="utf-8")
        return sk

    if setup == "scenario_temp_file":
        rel = "docs/scenario-temp.txt"
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text("temp\n", encoding="utf-8")
        return sk

    if setup == "u1_report_u2_empty":
        clear_report_cache()
        u1_sk = handler.resolve_session_key(
            session_key="wechat:u1",
            platform="wechat",
            external_id="u1",
        )
        cache_report(
            AgentReport(headline="report-for-u1-only", summary="u1"),
            session_key=u1_sk,
        )
        return sk

    if setup == "notes_on_disk":
        (proj / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")

    if setup == "copy_runtime_jobs":
        import shutil

        src = Path(__file__).resolve().parents[2] / "projects" / "DemoPilot" / "runtime" / "jobs.yaml"
        if src.is_file():
            dest = proj / "runtime"
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest / "jobs.yaml")

    if setup == "cached_report_delete_fail":
        clear_report_cache(sk)
        cache_report(
            AgentReport(
                headline="开发代理未能完成任务",
                task_preview="删除 docs/missing-utterance.txt",
                summary="删除未完成。",
                success=False,
                issues=["请使用 delete_file"],
            ),
            session_key=sk,
        )
        return sk

    apply_catalog_setup(
        entry,
        handler=handler,
        proj=proj,
        session_key=sk,
        helpers={
            **helpers,
            "bind_script": lambda script: _bind_llm_script(
                mock_complete, mock_stream, pad_script(script)
            ),
        },
    )
    return sk
