"""PROD-P5: Owner UX debt acceptance tests."""

from __future__ import annotations

import time

import pytest


@pytest.mark.unit
def test_p5_01_extract_task_id_from_completion_text():
    from butler.gateway.delegate_push_dedup import extract_task_id_from_text

    body = "内容代理已完成任务\n任务 task_a2b748f6d218 · 迭代 3 轮"
    assert extract_task_id_from_text(body) == "task_a2b748f6d218"


@pytest.mark.unit
def test_p5_01_dedup_blocks_second_push(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_PUSH_DEDUP", "1")
    from butler.gateway import delegate_push_dedup as mod

    mod._PUSHED.clear()
    chat = "wx:dedup-test"
    tid = "task_dedup001"
    ok1, _ = mod.should_deliver_delegate_push(chat, tid)
    assert ok1 is True
    mod.mark_delegate_push_delivered(chat, tid)
    ok2, reason = mod.should_deliver_delegate_push(chat, tid)
    assert ok2 is False
    assert "dedup" in reason


@pytest.mark.unit
def test_p5_01_stale_push_suppressed(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_PUSH_DEDUP", "1")
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_PUSH_MAX_AGE_SECONDS", "60")
    from butler.gateway import delegate_push_dedup as mod

    mod._PUSHED.clear()
    monkeypatch.setattr(
        mod,
        "_task_completed_epoch",
        lambda _tid: time.time() - 120,
    )
    ok, reason = mod.should_deliver_delegate_push("wx:stale", "task_stale001")
    assert ok is False
    assert reason.startswith("stale:")


@pytest.mark.unit
def test_p5_01_defers_push_during_inbound(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DEFER_DELEGATE_PUSH_DURING_INBOUND", "1")
    from butler.gateway.delegate_push_dedup import (
        flush_deferred_delegate_pushes,
        gateway_inbound_guard,
        is_inbound_active,
        maybe_defer_delegate_push,
    )

    chat = "wx:inbound"
    assert maybe_defer_delegate_push(chat, "任务 task_x", kind="delegate") is False
    with gateway_inbound_guard(chat):
        assert is_inbound_active(chat)
        assert maybe_defer_delegate_push(chat, "任务 task_x", kind="delegate") is True
    assert not is_inbound_active(chat)
    assert flush_deferred_delegate_pushes(chat) == []


@pytest.mark.unit
def test_p5_02_ingest_intent_detection():
    from butler.gateway.owner_ingest_shortcuts import looks_owner_ingest_intent

    assert looks_owner_ingest_intent(
        "把 docs/ext5-fixture-sample.txt 转成 Markdown 放进记忆"
    )
    assert looks_owner_ingest_intent(
        "把 docs/ext5-fixture-sample.txt 转成 Markdown 放进记忆 ingest"
    )
    assert not looks_owner_ingest_intent("把 docs/x 转成 Markdown")
    assert not looks_owner_ingest_intent("请记住：称呼主公")
    assert not looks_owner_ingest_intent("/简报")


@pytest.mark.unit
def test_p5_02_ingest_phrase_expands_to_mcp_ingest_path():
    from butler.gateway.owner_ingest_shortcuts import try_expand_owner_ingest_phrase

    text = "把 docs/ext5-fixture-sample.txt 转成 Markdown 放进记忆"
    out = try_expand_owner_ingest_phrase(
        text,
        project_name="灵文1号",
        workspace="/home/ailearn/projects/WFXM/projects/LingWen1",
    )
    assert out
    assert "MarkItDown MCP" in out
    assert "mcp_markitdown_convert_to_markdown" in out
    assert ".butler/ingest/docs/ext5-fixture-sample.md" in out
    assert "butler_remember" in out
    assert "不要反问" in out
    assert "ingest" in out.lower()


@pytest.mark.unit
def test_p5_02_edit_slash_takes_priority_over_ingest():
    from butler.gateway.owner_delegate_shortcuts import try_expand_owner_edit_slash
    from butler.gateway.owner_ingest_shortcuts import try_expand_owner_ingest_phrase

    text = "/改 docs/foo.md 加 ingest 说明"
    assert try_expand_owner_edit_slash(text, project_name="P") is not None
    assert try_expand_owner_ingest_phrase(text, project_name="P") is None


@pytest.mark.unit
def test_p5_03_ingest_delegate_success_without_verify_gate(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("BUTLER_DEV_VERIFY_SUCCESS_GATE", "1")
    from butler.dev_engine.b9_delegate_gate import apply_dev_auto_verify_success_gate
    from butler.report import AgentReport
    from butler.report.acceptance_card import (
        attach_delegate_acceptance_meta,
        format_delegate_acceptance_card,
    )
    from butler.tools.delegate_impl import finalize_delegate_success

    task = "【EXT-5 ingest 路由】把 docs/x.txt 转成 Markdown 放进 .butler/ingest/"
    changes = [
        SimpleNamespace(
            file="projects/LingWen1/.butler/ingest/docs/x.md",
            action="created",
        )
    ]
    dev_engine = {"edits": 1, "verify_passed": False}

    ok, issues = apply_dev_auto_verify_success_gate(
        role="dev",
        base_success=True,
        issues=[],
        dev_engine=dev_engine,
        task=task,
        changes=changes,
    )
    assert ok is True
    assert issues == []

    ok_code, code_issues = apply_dev_auto_verify_success_gate(
        role="dev",
        base_success=True,
        issues=[],
        dev_engine=dev_engine,
        task="fix butler/core/foo.py",
        changes=[SimpleNamespace(file="butler/core/foo.py", action="modified")],
    )
    assert ok_code is False
    assert any("DEV_VERIFY_GATE" in i for i in code_issues)

    result = SimpleNamespace(
        final_response="done",
        status=SimpleNamespace(value="completed"),
    )
    success, fin_issues = finalize_delegate_success(
        result,
        changes=changes,
        issues=[],
        role="dev",
        dev_engine=dev_engine,
        task=task,
    )
    assert success is True
    assert not any("DEV_VERIFY_GATE" in i for i in fin_issues)

    report = AgentReport(
        headline="开发代理已完成任务",
        summary="ingest ok",
        changes=changes,
        issues=fin_issues,
        success=success,
        task_preview=task[:200],
    )
    attach_delegate_acceptance_meta(
        report,
        role="dev",
        project=type("P", (), {"dev": {"test_command": "pytest"}})(),
        dev_engine=dev_engine,
        task=task,
    )
    card = format_delegate_acceptance_card(report)
    assert "ingest 写盘" in card
    assert "未通过" not in card
