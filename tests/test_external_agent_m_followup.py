"""Follow-up: inbound validate, handlers, until, agents.md, transcript, pending cancel."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from butler.agents_md import load_agent_md, merge_agent_md_into_context
from butler.core.message_ir import validate_openai_sequence
from butler.core.two_phase_confirm import (
    cancel_pending_unless_confirm,
    clear_pending,
    load_pending,
    save_pending,
)
from butler.gateway.inbound_validate import validate_loop_messages_before_turn
from butler.workflows.callbacks import WorkflowCallbackContext, run_workflow_handlers
from butler.workflows.until_assert import evaluate_until
from butler.workflows.schema import parse_step, parse_workflow_data


def test_validate_openai_sequence_orphan():
    errs = validate_openai_sequence([
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "x", "content": "r"},
    ])
    assert errs


def test_validate_loop_messages_blocks(monkeypatch):
    monkeypatch.setenv("BUTLER_INBOUND_SEQUENCE_VALIDATE", "1")
    err = validate_loop_messages_before_turn([
        {"role": "user", "content": "a"},
        {"role": "tool", "tool_call_id": "orphan", "content": "x"},
    ])
    assert err is not None
    assert "重置" in err


def test_until_output_contains():
    ok, err = evaluate_until("all tests passed successfully", {"output_contains": "passed"})
    assert ok and not err
    ok2, err2 = evaluate_until("failed", {"output_contains": "passed"})
    assert not ok2 and err2


def test_workflow_handlers_ledger():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        ctx = WorkflowCallbackContext(
            workflow_name="demo",
            workspace=ws,
            success=True,
            summary="ok",
        )
        run_workflow_handlers([{"type": "ledger"}], event="done", ctx=ctx)
        ledger = ws / ".butler" / "workflow_ledger.jsonl"
        assert ledger.is_file()


def test_parse_workflow_handlers_and_until():
    wf = parse_workflow_data({
        "name": "wf",
        "handlers": [{"type": "log"}, "notify"],
        "steps": [{
            "id": "s1",
            "role": "dev",
            "task": "t",
            "until": {"output_contains": "done"},
        }],
    })
    assert wf is not None
    assert len(wf.handlers) == 2
    assert wf.steps[0].until is not None


def test_agents_md_loader():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        agents_dir = ws / ".butler" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "reviewer.md").write_text(
            "---\nname: reviewer\ndescription: code review\n---\n\nReview only.\n",
            encoding="utf-8",
        )
        agent = load_agent_md(ws, "reviewer")
        assert agent is not None
        assert "Review only" in agent.system_prompt
        merged = merge_agent_md_into_context(ws, "reviewer", "base")
        assert "Review only" in merged


def test_cancel_pending_unless_confirm(monkeypatch):
    monkeypatch.setenv("BUTLER_TWO_PHASE_CONFIRM", "1")
    clear_pending("cancel-s")
    save_pending("delete_file", {"path": "x"}, session_key="cancel-s")
    note = cancel_pending_unless_confirm("普通问题", session_key="cancel-s")
    assert note is not None
    assert load_pending("cancel-s") is None


def test_record_tool_action_transcript(monkeypatch):
    from butler.core.session_transcript import (
        load_transcript_tail,
        record_tool_action,
        record_tool_observation,
    )

    home = Path(tempfile.mkdtemp())
    import butler.config as cfg

    monkeypatch.setattr(cfg, "get_butler_home", lambda: home)
    record_tool_action("sk1", tool_name="read_file", args_preview='{"path":"a"}')
    record_tool_observation("sk1", tool_name="read_file", outcome="ok", preview="ok")
    rows = load_transcript_tail("sk1", max_lines=10)
    types = {r.get("type") for r in rows}
    assert "tool_action" in types
    assert "tool_observation" in types
