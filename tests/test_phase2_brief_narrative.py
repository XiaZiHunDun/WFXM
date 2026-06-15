"""Phase 2: WS-E brief/inbox + WS-F tool narrative."""

from __future__ import annotations

import json

from butler.core.tool_narrative import describe_tool_action, format_session_tool_narrative
from butler.ops.butler_inbox import collect_inbox_snapshot, format_owner_brief


class _Proj:
    name = "灵文1号"
    workspace = "/tmp/lingwen"


class _PM:
    def get_current(self, *, session_key: str = ""):
        return _Proj()

    def resolve_active_project_name(self, *, session_key: str = ""):
        return "灵文1号"


class _Orch:
    project_manager = _PM()

    def _reload_project_memory(self) -> None:
        return None

    @property
    def _project_memory(self):
        return None


def test_describe_tool_action_read_file():
    line = describe_tool_action(
        "read_file",
        json.dumps({"path": "docs/README.md"}),
        source="loop",
    )
    assert "读取" in line
    assert "docs/README.md" in line


def test_describe_tool_action_delegate_shows_role():
    line = describe_tool_action(
        "delegate_task",
        json.dumps({"role": "dev", "task": "fix import"}),
        source="loop",
    )
    assert "委派" in line
    assert "dev" in line


def test_format_owner_brief_empty_inbox(monkeypatch):
    monkeypatch.setattr(
        "butler.tools.project_todos._load",
        lambda _ws: [],
    )
    monkeypatch.setattr(
        "butler.tools.reminder._load_all",
        lambda: [],
    )
    text = format_owner_brief(_Orch(), "wechat:u:灵文1号")
    assert "管家简报" in text
    assert "灵文1号" in text
    assert "暂无待处理" in text


def test_collect_inbox_counts_project_todos(monkeypatch, tmp_path):
    ws = tmp_path / "proj"
    (ws / ".butler").mkdir(parents=True)
    monkeypatch.setattr(
        "butler.tools.project_todos._load",
        lambda _ws: [{"content": "写第三章", "status": "pending"}],
    )
    monkeypatch.setattr(
        "butler.tools.reminder._load_all",
        lambda: [],
    )

    class _P:
        name = "灵文1号"
        workspace = str(ws)

    class _PM2:
        def get_current(self, *, session_key: str = ""):
            return _P()

        def resolve_active_project_name(self, *, session_key: str = ""):
            return "灵文1号"

    orch = _Orch()
    orch.project_manager = _PM2()
    snap = collect_inbox_snapshot(orch, "wechat:u:灵文1号")
    assert snap.project_todos_open == 1
    assert "写第三章" in snap.project_todo_samples[0]


def test_format_session_tool_narrative_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    text = format_session_tool_narrative("sk:empty")
    assert "尚无工具调用" in text
