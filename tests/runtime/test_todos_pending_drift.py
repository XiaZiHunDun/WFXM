"""builtin:todos_pending_drift — drift between .butler/todos.json and MEMORY.md ## Pending.

Read-only collector tests + builtin handler smoke.
"""

from __future__ import annotations

from pathlib import Path

from butler.runtime.builtin_handlers import run_builtin
from butler.tools.project_todos import _save as save_todos
from butler.tools.project_todos_drift_ops import collect_todos_pending_drift


def _setup_workspace(tmp_path: Path) -> Path:
    (tmp_path / ".butler" / "memory").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _seed_todos(tmp_path: Path, items: list[dict]) -> None:
    save_todos(tmp_path, items)


def _seed_memory(tmp_path: Path, content: str) -> None:
    (tmp_path / ".butler" / "memory" / "MEMORY.md").write_text(content, encoding="utf-8")


class TestCollectTodosPendingDrift:
    def test_no_drift_when_stores_consistent(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        _seed_todos(tmp_path, [
            {"id": "lw-t01", "content": "Agent JSON schema 校验", "status": "pending", "priority": "high"},
        ])
        _seed_memory(tmp_path, (
            "## Pending\n"
            "- [PENDING] [target:Notes] [2026-07-10 10:00] Agent JSON schema 校验\n"
        ))
        drift = collect_todos_pending_drift(tmp_path)
        assert drift["counts"]["todos_open"] == 1
        assert drift["counts"]["pending_open"] == 1
        assert drift["counts"]["drift_total"] == 0
        assert drift["completed_todo_with_open_pending"] == []
        assert drift["pending_with_no_todo"] == []
        assert drift["open_todo_with_no_pending"] == []

    def test_completed_todo_with_open_pending_flagged(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        _seed_todos(tmp_path, [
            {"id": "lw-t01", "content": "Agent JSON schema 校验", "status": "completed", "priority": "high"},
        ])
        _seed_memory(tmp_path, (
            "## Pending\n"
            "- [PENDING] [target:Notes] [2026-07-10 10:00] Agent JSON schema 校验\n"
        ))
        drift = collect_todos_pending_drift(tmp_path)
        assert drift["counts"]["drift_total"] == 1
        assert len(drift["completed_todo_with_open_pending"]) == 1
        row = drift["completed_todo_with_open_pending"][0]
        assert row["todo"]["id"] == "lw-t01"
        assert row["pending"]["content"] == "Agent JSON schema 校验"

    def test_pending_with_no_todo_flagged(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        _seed_todos(tmp_path, [])
        _seed_memory(tmp_path, (
            "## Pending\n"
            "- [PENDING] [target:Notes] [2026-07-10 10:00] workflow_state 微信口径对齐\n"
        ))
        drift = collect_todos_pending_drift(tmp_path)
        assert drift["counts"]["drift_total"] == 1
        assert drift["counts"]["todos_open"] == 0
        assert drift["counts"]["pending_open"] == 1
        assert len(drift["pending_with_no_todo"]) == 1
        assert drift["pending_with_no_todo"][0]["pending"]["content"] == "workflow_state 微信口径对齐"

    def test_normalized_key_matches_verb_variants(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        _seed_todos(tmp_path, [
            {"id": "lw-t01", "content": "补 Agent JSON schema 校验：novel-factory 三处 Agent 缺 schema", "status": "pending", "priority": "high"},
        ])
        _seed_memory(tmp_path, (
            "## Pending\n"
            "- [PENDING] [target:Notes] [2026-07-10 10:00] Agent JSON schema 校验：novel-factory 三处 Agent 缺 schema\n"
        ))
        drift = collect_todos_pending_drift(tmp_path)
        assert drift["counts"]["drift_total"] == 0
        assert drift["open_todo_with_no_pending"] == []
        assert drift["pending_with_no_todo"] == []

    def test_open_todo_with_no_pending_flagged(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        _seed_todos(tmp_path, [
            {"id": "lw-t09", "content": "整理 weekly 一致性报告模板", "status": "pending", "priority": "medium"},
        ])
        _seed_memory(tmp_path, "## Pending\n")
        drift = collect_todos_pending_drift(tmp_path)
        assert drift["counts"]["drift_total"] == 1
        assert len(drift["open_todo_with_no_pending"]) == 1
        assert drift["open_todo_with_no_pending"][0]["todo"]["id"] == "lw-t09"

    def test_drift_returns_full_lists_not_capped(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        _seed_todos(tmp_path, [])
        mem_lines = ["## Pending"]
        for i in range(10):
            mem_lines.append(
                f"- [PENDING] [target:Notes] [2026-07-10 10:0{i % 10}] stale item {i}"
            )
        _seed_memory(tmp_path, "\n".join(mem_lines) + "\n")
        drift = collect_todos_pending_drift(tmp_path)
        # collector 返回完整列表，cap 由 _format_drift_summary 负责
        assert drift["counts"]["pending_open"] == 10
        assert drift["counts"]["drift_total"] == 10
        assert len(drift["pending_with_no_todo"]) == 10

    def test_handles_missing_memory_file(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        _seed_todos(tmp_path, [
            {"id": "lw-t01", "content": "仅存于 todo", "status": "pending", "priority": "medium"},
        ])
        # 无 MEMORY.md
        drift = collect_todos_pending_drift(tmp_path)
        assert drift["counts"]["pending_open"] == 0
        assert drift["counts"]["drift_total"] == 1
        assert len(drift["open_todo_with_no_pending"]) == 1

    def test_handles_corrupt_todos_json(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        todos_path = tmp_path / ".butler" / "todos.json"
        todos_path.parent.mkdir(parents=True, exist_ok=True)
        todos_path.write_text("not-valid-json{", encoding="utf-8")
        _seed_memory(tmp_path, "## Pending\n")
        drift = collect_todos_pending_drift(tmp_path)
        assert drift["counts"]["todos_open"] == 0
        assert drift["counts"]["drift_total"] == 0


class TestBuiltinTodosPendingDrift:
    def test_builtin_handler_runs_against_tmp_workspace(self, tmp_path: Path):
        _setup_workspace(tmp_path)
        _seed_todos(tmp_path, [
            {"id": "lw-t01", "content": "补 Agent JSON schema 校验", "status": "pending", "priority": "high"},
        ])
        _seed_memory(tmp_path, (
            "## Pending\n"
            "- [PENDING] [target:Notes] [2026-07-10 10:00] Agent JSON schema 校验\n"
        ))
        result = run_builtin("builtin:todos_pending_drift", tmp_path)
        assert result["success"] is True
        assert "drift:" in result["summary"]
        assert "todos_open=1" in result["summary"]
        assert "pending_open=1" in result["summary"]
        assert result["stderr"] == ""
