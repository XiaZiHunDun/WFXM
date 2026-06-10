"""builtin:experience_mining_weekly runtime handler."""

from __future__ import annotations

from pathlib import Path

from butler.runtime.builtin_handlers import run_builtin


def test_experience_mining_weekly_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUTLER_EXPERIENCE_MINING", "0")
    result = run_builtin("builtin:experience_mining_weekly", tmp_path)
    assert result["success"] is True
    assert "已跳过" in result["summary"]


def test_experience_mining_weekly_runs_pipeline(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "butler"))
    monkeypatch.setenv("BUTLER_EXPERIENCE_MINING", "1")
    monkeypatch.setenv("BUTLER_EXPERIENCE_MINING_AUTO_INGEST", "0")

    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "pyproject.toml").write_text('[project]\nname="demo"\n', encoding="utf-8")

    result = run_builtin("builtin:experience_mining_weekly", ws)
    assert result["success"] is True
    assert "经验挖掘" in result["summary"]
    assert "候选:" in result["stdout"]
