"""character_waivers.yaml schema validation."""

from pathlib import Path

import yaml

WAIVERS = (
    Path(__file__).resolve().parents[1]
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "tools"
    / "consistency"
    / "character_waivers.yaml"
)


def test_character_waivers_yaml_valid():
    assert WAIVERS.is_file()
    data = yaml.safe_load(WAIVERS.read_text(encoding="utf-8")) or {}
    rows = data.get("suppress_alive_conflict")
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict), row
        assert str(row.get("char") or "").strip()
        assert row.get("chapter") is not None
        int(row["chapter"])
