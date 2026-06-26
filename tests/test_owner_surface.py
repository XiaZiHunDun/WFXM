"""Tests for Owner UX surfaces (help tiers, approval cards, status)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from butler.gateway.approval_cards import (
    format_terminal_exec_card,
    format_terminal_pattern_card,
    format_terminal_sandbox_card,
)
from butler.gateway.commands.help_handlers import format_help_text
from butler.gateway.owner_surface import (
    format_cc_complement_message,
    format_owner_diagnostic_brief,
    format_owner_help_default,
    format_project_switch_brief,
    format_project_today_view,
)


def test_default_help_is_tier1():
    text = format_help_text()
    assert "查" in text and "改" in text and "批" in text
    assert "/简报" in text
    assert "/帮助 高级" in text or "高级" in text
    assert len(text.splitlines()) < 20


def test_advanced_help_topic():
    text = format_help_text("高级")
    assert "全部命令" in text or "主题" in text


def test_terminal_exec_card_has_copy_line():
    card = format_terminal_exec_card("ls -la")
    assert "【需要您批准】" in card
    assert "/批准执行 ls -la" in card


def test_terminal_sandbox_card():
    card = format_terminal_sandbox_card("curl https://x.com", constraint="network")
    assert "/批准沙箱外" in card
    assert "network" in card


def test_terminal_pattern_card():
    card = format_terminal_pattern_card("rm_rf", command_preview="rm -rf /tmp/x")
    assert "/批准模式 rm_rf" in card


def test_project_switch_brief_includes_todos(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    todos = ws / ".butler" / "todos.json"
    todos.parent.mkdir(parents=True)
    todos.write_text(
        '[{"content":"fix bug","status":"pending"}]',
        encoding="utf-8",
    )
    orch = MagicMock()
    proj = SimpleNamespace(
        name="Demo",
        workspace=ws,
        pack="",
        status="active",
        lifecycle="",
        lead=None,
    )
    orch.project_manager.get_project.return_value = proj
    orch.project_manager.get_current.return_value = proj
    orch._settings.default_provider = "minimax"

    brief = format_project_switch_brief(orch, "sk1", "Demo")
    assert "项目摘要" in brief
    assert "待办" in brief


def test_owner_help_default_five_intents():
    text = format_owner_help_default()
    assert "五个说法" in text
    for kw in ("查", "改", "批", "记", "管"):
        assert kw in text
    assert "高级" in text


def test_owner_diagnostic_brief_three_lines():
    orch = MagicMock()
    orch._settings.default_provider = "minimax"
    orch.project_manager.get_current.return_value = SimpleNamespace(name="Demo")
    text = format_owner_diagnostic_brief(orch, "sk1")
    assert "简要诊断" in text
    assert "网关：" in text
    assert "项目：" in text
    assert "待办：" in text
    assert "OT2" not in text
    assert "G1-04" not in text
    assert "部署剖面" not in text


@patch("butler.gateway.owner_surface._owner_outbound_brief_line", return_value="出站：🔴 有 2 条发送失败 → 运维见 wechat-gateway-ops · /诊断 详细")
def test_owner_diagnostic_brief_shows_outbound_issue(_mock_outbound):
    orch = MagicMock()
    orch._settings.default_provider = "minimax"
    orch.project_manager.get_current.return_value = SimpleNamespace(name="Demo")
    text = format_owner_diagnostic_brief(orch, "sk1")
    assert "发送失败" in text
    assert "wechat-gateway-ops" in text


@patch("butler.gateway.durable_outbox.outbox_counts", return_value={"pending": 0, "sent": 1, "failed": 2})
@patch("butler.gateway.completion_telemetry.push_queue_pending_count", return_value=0)
@patch(
    "butler.gateway.completion_telemetry.completion_push_stats",
    return_value={"sent": 0, "failed": 0, "enqueued": 0},
)
def test_owner_outbound_brief_line_failed_outbox(_stats, _queue, _counts):
    from butler.gateway.owner_surface import _owner_outbound_brief_line

    line = _owner_outbound_brief_line(session_key="wechat:x:Demo")
    assert line is not None
    assert "发送失败" in line
    assert "2" in line
    assert "/诊断 详细" in line


def test_brief_includes_health_header():
    from butler.ops.butler_inbox import format_owner_brief

    orch = MagicMock()
    orch._settings.default_provider = "minimax"
    orch.project_manager.get_current.return_value = SimpleNamespace(name="Demo")
    text = format_owner_brief(orch, "sk1")
    assert "健康概览" in text
    assert "管家简报" in text
    assert "【待办】" in text
    assert "【队列】" in text


def test_terminal_approval_message_no_double_wrap():
    from butler.gateway.approval_cards import (
        format_terminal_approval_message,
        format_terminal_exec_card,
    )

    card = format_terminal_exec_card("ls")
    wrapped = format_terminal_approval_message("ls", card)
    assert wrapped == card
    assert wrapped.count("【需要您批准】") == 1


def test_terminal_approval_expired_returns_card():
    from butler.tools.terminal_approval import check_approval

    with patch.dict("os.environ", {"BUTLER_TERMINAL_REQUIRE_APPROVAL": "1"}):
        with patch("butler.tools.terminal_approval._approvals_dir") as mock_dir:
            path = MagicMock()
            path.is_file.return_value = True
            path.read_text.return_value = '{"expires_at": 0, "command": "ls"}'
            mock_dir.return_value.__truediv__.return_value = path
            msg = check_approval("ls", session_key="sk1")
    assert "【需要您批准】" in msg
    assert "/批准执行" in msg


def test_project_today_view():
    orch = MagicMock()
    orch._settings.default_provider = "minimax"
    orch.project_manager.get_current.return_value = SimpleNamespace(name="Demo")
    text = format_project_today_view(orch, "sk1")
    assert "今日" in text
    assert "优先事项" in text
    assert "健康概览" in text


def test_cc_complement_message():
    text = format_cc_complement_message()
    assert "Claude Code" in text
    assert "委派" in text


def test_memory_recap_with_snippets():
    from butler.core.memory_recap_line import build_memory_recap_line, maybe_prepend_memory_recap

    health = {
        "memory_context_injected": True,
        "memory_last_turn_sources": {
            "snippet_samples": ["用户偏好 pytest 做验收"],
        },
    }
    line = build_memory_recap_line(health=health)
    assert line and "记得" in line
    long_out = "x" * 400
    merged = maybe_prepend_memory_recap("sk", long_out, health=health)
    assert merged.startswith("💭")


def test_project_overview_owner():
    from butler.gateway.owner_surface import format_project_overview_owner
    from butler.ops.butler_inbox import InboxSnapshot

    orch = MagicMock()
    orch._settings.default_provider = "minimax"
    ws = Path("/tmp/demo_proj")
    proj = SimpleNamespace(name="Demo", workspace=ws, pack="", dev={}, lead=None)
    orch.project_manager.get_current.return_value = proj

    snap = InboxSnapshot(
        project_todos_open=1,
        project_todo_samples=["fix bug"],
    )

    with (
        patch.object(Path, "is_dir", return_value=True),
        patch(
            "butler.gateway.owner_surface._runtime_jobs_owner_lines",
            return_value=["· 定时任务 2 个：heartbeat"],
        ),
        patch(
            "butler.ops.butler_inbox.collect_inbox_snapshot",
            return_value=snap,
        ),
        patch(
            "butler.project.lead.is_lead_project",
            return_value=False,
        ),
        patch(
            "butler.project.meta.lifecycle_label",
            return_value="active",
        ),
    ):
        text = format_project_overview_owner(orch, "sk1")

    assert "项目概况" in text
    assert "今日焦点" in text
    assert "详细" in text


def test_memory_auto_classify_sensitive_goes_pending(tmp_path):
    from butler.memory.project_memory import MarkdownMemory

    mm = MarkdownMemory(tmp_path / "MEMORY.md")
    assert mm.append("Notes", "Owner 手机 13800138000", classification="auto") == "pending"
    assert mm.list_pending()


def test_memory_auto_classify_low_risk_fact(tmp_path, monkeypatch):
    from butler.memory.project_memory import MarkdownMemory

    monkeypatch.delenv("BUTLER_MEMORY_AUTO_APPROVE", raising=False)
    mm = MarkdownMemory(tmp_path / "MEMORY.md")
    assert mm.append("Notes", "默认测试框架为 pytest", classification="auto") == "fact"
    assert not mm.list_pending()


def test_memory_auto_fact_disabled(tmp_path, monkeypatch):
    from butler.memory.project_memory import MarkdownMemory

    monkeypatch.setenv("BUTLER_MEMORY_AUTO_FACT", "0")
    mm = MarkdownMemory(tmp_path / "MEMORY.md")
    assert mm.append("Notes", "默认测试框架为 pytest", classification="auto") == "pending"
