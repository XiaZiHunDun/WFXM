"""Hermes subprocess path helpers (gateway --hermes-fallback)."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.hermes_runtime import hermes_cli_main, hermes_repo_root


@pytest.mark.unit
def test_hermes_repo_root_points_at_vendor():
    root = hermes_repo_root()
    assert root.name == "hermes-agent"
    assert "vendor" in root.parts
    assert (root / "hermes_cli").is_dir()
    assert (root / "agent").is_dir()
    assert hermes_cli_main().name == "main.py"


@pytest.mark.unit
def test_hermes_repo_root_raises_when_tree_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.hermes_runtime._HERMES_ROOT", tmp_path / "vendor" / "hermes-agent")
    with pytest.raises(FileNotFoundError, match="Hermes vendored tree missing"):
        hermes_repo_root()
