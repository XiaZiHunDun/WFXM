"""Pilot projects must declare dev.*_command for VERIFY (PROD-P1-01)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]

_PILOTS = (
    ("DemoPilot", "演示试点"),
    ("LingWen1", "灵文1号"),
)


@pytest.mark.unit
@pytest.mark.parametrize("slug,_name", _PILOTS)
def test_pilot_project_yaml_has_dev_commands(slug: str, _name: str):
    cfg = _REPO / "projects" / slug / "project.yaml"
    assert cfg.is_file(), f"missing {cfg}"
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    dev = data.get("dev") or {}
    assert str(dev.get("test_command") or "").strip(), f"{slug}: dev.test_command required"
    assert str(dev.get("lint_command") or "").strip(), f"{slug}: dev.lint_command required"
