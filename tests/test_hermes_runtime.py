"""Hermes subprocess path helpers (gateway --hermes-fallback)."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.hermes_runtime import hermes_cli_main, hermes_repo_root


@pytest.mark.unit
def test_hermes_repo_root_points_at_repo_or_vendor():
    root = hermes_repo_root()
    assert (root / "hermes_cli").is_dir()
    assert hermes_cli_main().name == "main.py"
    assert hermes_cli_main().parent.name == "hermes_cli"


@pytest.mark.unit
def test_vendor_root_preferred_when_present(tmp_path, monkeypatch):
    vendor = tmp_path / "vendor" / "hermes-agent"
    (vendor / "hermes_cli").mkdir(parents=True)
    (vendor / "hermes_cli" / "main.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setattr("butler.hermes_runtime._VENDOR_ROOT", vendor)
    monkeypatch.setattr("butler.hermes_runtime._REPO_ROOT", tmp_path)
    assert hermes_repo_root() == vendor
    assert hermes_cli_main() == vendor / "hermes_cli" / "main.py"
