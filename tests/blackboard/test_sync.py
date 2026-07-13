"""sync：backlog.yaml ↔ ~/.butler/todos.json 双向同步。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.blackboard.sync import sync_todos_from_backlog, sync_backlog_from_todos
from butler.blackboard.task_io import load_backlog, save_backlog
from butler.blackboard.schema import BacklogFile, BacklogTask, Priority, TaskStatus


@pytest.fixture
def fake_butler_home(tmp_butler_home, monkeypatch):
    """把 BUTLER_HOME 指向带 todos.json 的临时 .butler/。
    复用 tests/conftest.py 的 autouse tmp_butler_home（已 mkdir + setenv）。
    """
    (tmp_butler_home / "todos.json").write_text(json.dumps({
        "items": [
            {"id": "P3-#11", "title": "from todos", "status": "open", "priority": "P3"},
            {"id": "P3-#12", "title": "another", "status": "open", "priority": "P3"},
        ]
    }))
    return tmp_butler_home


def test_sync_todos_from_backlog_appends_new(fake_butler_home, tmp_blackboard):
    """backlog 中没有但 todos.json 有的项 → append 到 backlog。"""
    bf = BacklogFile(last_updated="2026-07-13T00:00:00+08:00", tasks=[
        BacklogTask(id="P1-#4", title="x", priority=Priority.P1, status=TaskStatus.OPEN),
    ])
    save_backlog(bf)
    added = sync_todos_from_backlog()
    assert added == ["P3-#11", "P3-#12"]
    loaded = load_backlog()
    assert {t.id for t in loaded.tasks} == {"P1-#4", "P3-#11", "P3-#12"}


def test_sync_backlog_to_todos(fake_butler_home, tmp_blackboard):
    """backlog 状态推回 todos.json。"""
    bf = BacklogFile(last_updated="2026-07-13T00:00:00+08:00", tasks=[
        BacklogTask(id="P3-#11", title="updated", priority=Priority.P3, status=TaskStatus.IN_PROGRESS),
    ])
    save_backlog(bf)
    n = sync_backlog_from_todos()
    assert n == 1
    data = json.loads((fake_butler_home / "todos.json").read_text())
    item = next(i for i in data["items"] if i["id"] == "P3-#11")
    assert item["title"] == "updated"
    assert item["status"] == "in_progress"