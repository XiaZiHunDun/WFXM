"""builtin:memory_offline_consolidate runtime handler."""

from __future__ import annotations

from pathlib import Path

from butler.runtime.builtin_handlers import run_builtin


def test_memory_offline_consolidate(tmp_path: Path, monkeypatch, tmp_butler_home):
    monkeypatch.setenv("BUTLER_EXPERIENCE_PRUNE_DAYS", "30")
    result = run_builtin("builtin:memory_offline_consolidate", tmp_path)
    assert result["success"] is True
    assert "记忆离线整理" in result["summary"]
