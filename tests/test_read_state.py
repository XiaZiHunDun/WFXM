"""Read-before-edit + mtime guard."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from butler.core.read_state import (
    check_read_state_for_resolved,
    read_before_edit_enabled,
    record_read_state,
    require_read_before_edit,
    reset_read_state,
)
from butler.execution_context import use_execution_context
from butler.tools.registry import dispatch_tool


def _orchestrator_for_workspace(workspace: Path):
    orch = MagicMock()  # noqa: magicmock-no-spec — read state facade (orch)
    orch.project_manager.get_current.return_value = SimpleNamespace(workspace=workspace)
    return orch


@pytest.fixture(autouse=True)
def _tool_safe_root(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))


@pytest.mark.unit
def test_read_before_edit_enabled_default(monkeypatch):
    monkeypatch.delenv("BUTLER_READ_BEFORE_EDIT", raising=False)
    assert read_before_edit_enabled() is True


@pytest.mark.unit
def test_require_blocks_without_read(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_READ_BEFORE_EDIT", "1")
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    reset_read_state("_global")
    err = check_read_state_for_resolved(f.resolve())
    assert err is not None
    assert err["code"] == "READ_STATE_REQUIRED"
    assert "hint" in err
    assert "read_file" in err["hint"].lower()


@pytest.mark.unit
def test_require_allows_after_read(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_READ_BEFORE_EDIT", "1")
    f = tmp_path / "b.txt"
    f.write_text("line", encoding="utf-8")
    reset_read_state("_global")
    st = f.stat()
    record_read_state(f, st, f.read_bytes())
    assert check_read_state_for_resolved(f.resolve()) is None


@pytest.mark.unit
def test_stale_mtime_blocks_edit(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_READ_BEFORE_EDIT", "1")
    f = tmp_path / "c.txt"
    f.write_text("v1", encoding="utf-8")
    reset_read_state("_global")
    st = f.stat()
    record_read_state(f, st, f.read_bytes())
    f.write_text("v2", encoding="utf-8")
    new_st = f.stat()
    os.utime(
        f,
        ns=(new_st.st_atime_ns, st.st_mtime_ns + 5_000_000_000),
    )
    err = check_read_state_for_resolved(f.resolve())
    assert err is not None
    assert err["code"] == "READ_STATE_STALE"


_SK = "test-read-state"


@pytest.mark.module_test
def test_patch_requires_read_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_READ_BEFORE_EDIT", "1")
    reset_read_state(_SK)
    f = tmp_path / "p.txt"
    f.write_text("alpha", encoding="utf-8")
    with use_execution_context(_orchestrator_for_workspace(tmp_path), session_key=_SK):
        result = dispatch_tool(
            "patch",
            {"path": str(f), "old_string": "alpha", "new_string": "beta"},
        )
    data = json.loads(result)
    assert data["code"] == "READ_STATE_REQUIRED"


@pytest.mark.module_test
def test_patch_after_read_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_READ_BEFORE_EDIT", "1")
    reset_read_state(_SK)
    f = tmp_path / "q.txt"
    f.write_text("foo bar", encoding="utf-8")
    with use_execution_context(_orchestrator_for_workspace(tmp_path), session_key=_SK):
        dispatch_tool("read_file", {"path": str(f)})
        result = dispatch_tool(
            "patch",
            {"path": str(f), "old_string": "bar", "new_string": "BAZ"},
        )
    data = json.loads(result)
    assert data.get("success") is True
    assert f.read_text(encoding="utf-8") == "foo BAZ"


@pytest.mark.module_test
def test_write_existing_requires_read(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_READ_BEFORE_EDIT", "1")
    reset_read_state(_SK)
    f = tmp_path / "w.txt"
    f.write_text("old", encoding="utf-8")
    with use_execution_context(_orchestrator_for_workspace(tmp_path), session_key=_SK):
        result = dispatch_tool("write_file", {"path": str(f), "content": "new"})
    data = json.loads(result)
    assert data["code"] == "READ_STATE_REQUIRED"


@pytest.mark.module_test
def test_write_new_file_without_read(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_READ_BEFORE_EDIT", "1")
    reset_read_state(_SK)
    f = tmp_path / "new-only.txt"
    with use_execution_context(_orchestrator_for_workspace(tmp_path), session_key=_SK):
        result = dispatch_tool("write_file", {"path": str(f), "content": "fresh"})
    data = json.loads(result)
    assert data.get("success") is True
