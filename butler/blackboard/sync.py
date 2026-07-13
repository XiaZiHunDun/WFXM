"""Backlog ↔ ~/.butler/todos.json 同步。

策略：单向为主（backlog → todos），反向需要 --from-todos 显式调用，
避免双向同步的复杂度。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from butler.blackboard.schema import BacklogFile, BacklogTask, Priority, TaskStatus
from butler.blackboard.task_io import load_backlog, save_backlog


def _todos_path() -> Path:
    """从 BUTLER_HOME 推断 todos.json 路径；默认 ~/.butler/todos.json。"""
    home = os.environ.get("BUTLER_HOME") or str(Path.home() / ".butler")
    return Path(home) / "todos.json"


def sync_todos_from_backlog() -> list[str]:
    """把 backlog 中没有但 todos.json 有的项追加到 backlog。

    返回新追加的 task id 列表。
    """
    bf = load_backlog()
    existing_ids = {t.id for t in bf.tasks}
    path = _todos_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    added: list[str] = []
    for item in items:
        tid = item.get("id")
        if not tid or tid in existing_ids:
            continue
        bf.tasks.append(BacklogTask(
            id=tid,
            title=item.get("title", ""),
            priority=Priority(item.get("priority", "P3")),
            status=TaskStatus(item.get("status", "open")),
        ))
        added.append(tid)
    if added:
        bf.last_updated = datetime.now().isoformat(timespec="seconds")
        save_backlog(bf)
    return added


def sync_backlog_from_todos() -> int:
    """把 backlog 状态反向推到 todos.json。

    返回更新的 item 数。
    """
    path = _todos_path()
    if not path.exists():
        return 0
    bf = load_backlog()
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    by_id = {i["id"]: i for i in items if "id" in i}
    n = 0
    for t in bf.tasks:
        if t.id in by_id:
            by_id[t.id]["status"] = t.status.value
            by_id[t.id]["title"] = t.title
            n += 1
    data["items"] = list(by_id.values())
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return n