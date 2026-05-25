"""Prompt Corpus line (phase D/E) — tool DSL, plan mode, transcript, partial read."""

from __future__ import annotations

import json
from pathlib import Path
from butler.core.read_file_partial import (
    build_large_file_summary,
    format_summary_message,
    read_summary_threshold_lines,
)
from butler.core.session_transcript import (
    record_knowledge_inject,
    record_plan_step,
    record_tool_observation,
    transcript_path,
)
from butler.core.transcript_retention import (
    select_transcript_rows_for_retention,
    transcript_keep_priority,
)
from butler.gateway.task_milestone import build_milestone_text, task_milestone_enabled
from butler.plan_mode import check_plan_mode_block, clear_plan_mode, set_plan_mode
from butler.tools.project_tools import allowed_tool_names_for_project
from butler.tools.registry import get_tool_definitions
from butler.tools.tool_doc_templates import (
    enrich_tool_description,
    tool_description_has_not_section,
)


def test_tool_description_includes_when_not():
    desc = enrich_tool_description("read_file", "Read a file.")
    assert tool_description_has_not_section(desc)
    assert "何时不要用" in desc


def test_core_tools_have_not_section_in_registry():
    get_tool_definitions()  # ensures builtins registered
    names = {"read_file", "search_files", "delegate_task", "terminal", "patch"}
    by_name = {
        t["function"]["name"]: t["function"]["description"]
        for t in get_tool_definitions()
    }
    for n in names:
        assert n in by_name, n
        assert tool_description_has_not_section(by_name[n]), n


def test_plan_mode_tools_exclude_terminal(tmp_path, monkeypatch):
    clear_plan_mode("pc-plan-tools")
    allowed = allowed_tool_names_for_project(None, role="plan")
    assert "read_file" in allowed
    assert "terminal" not in allowed
    assert "delegate_task" not in allowed


def test_plan_mode_blocks_terminal_after_enable():
    sk = "pc-plan-block"
    clear_plan_mode(sk)
    set_plan_mode(sk, True)
    msg = check_plan_mode_block("terminal", {"command": "ls"}, session_key=sk)
    assert msg and "规划模式" in msg
    clear_plan_mode(sk)


def test_transcript_event_priorities():
    assert transcript_keep_priority("plan_step") > transcript_keep_priority("queue_op")
    rows = [
        {"type": "queue_op", "preview": "a"},
        {"type": "plan_step", "title": "b"},
        {"type": "user", "content_preview": "c"},
    ]
    kept = select_transcript_rows_for_retention(rows, keep_count=2)
    types = [r["type"] for r in kept]
    assert "plan_step" in types
    assert "queue_op" not in types


def test_record_plan_and_knowledge_events(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "bh"))
    sk = "pc-transcript"
    record_plan_step(sk, title="t1", phase="start")
    record_knowledge_inject(sk, chars=42)
    record_tool_observation(sk, tool="read_file", ok=True, preview="ok")
    path = transcript_path(sk)
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    types = [json.loads(ln)["type"] for ln in lines]
    assert "plan_step" in types
    assert "knowledge_inject" in types
    assert "tool_observation" in types


def test_large_file_summary_contract():
    lines = ["# Title\n"] + [f"line {i}" for i in range(500)]
    summary = build_large_file_summary("big.py", lines)
    text = format_summary_message(summary)
    assert "大文件摘要" in text
    assert "offset=" in text
    assert summary["total_lines"] == len(lines)


def test_read_summary_threshold_sane():
    assert read_summary_threshold_lines() >= 50


def test_plan_mode_prompt_file_exists():
    path = Path(__file__).resolve().parents[1] / "butler" / "prompts" / "butler_plan_mode.md"
    assert path.is_file()
    assert "规划模式" in path.read_text(encoding="utf-8")


def test_task_milestone_text_format():
    from butler.gateway.outbound_bridge import GatewayOutboundBridge

    class _Adapter:
        async def send_typing(self, *a, **k):
            pass

        async def stop_typing(self, *a, **k):
            pass

        async def send(self, *a, **k):
            pass

    import asyncio

    loop = asyncio.new_event_loop()
    bridge = GatewayOutboundBridge(adapter=_Adapter(), chat_id="c1", loop=loop)
    bridge.delegate_role = "dev"
    text = build_milestone_text(bridge, elapsed=120)
    assert "【进度】" in text
    assert "委派" in text
    loop.close()


def test_butler_system_has_agent_discipline():
    path = Path(__file__).resolve().parents[1] / "butler" / "prompts" / "butler_system.md"
    body = path.read_text(encoding="utf-8")
    assert "<agent_discipline>" in body
    assert "批量" in body
