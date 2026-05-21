"""Regression: alive→death is plot; only death→alive is ALIVE_CONFLICT."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LW_TOOLS = ROOT / "projects" / "LingWen1" / "novel-factory" / "tools" / "consistency"
if str(LW_TOOLS) not in sys.path:
    sys.path.insert(0, str(LW_TOOLS))

from check_character_state import check_character_consistency  # noqa: E402


def test_alive_to_death_not_flagged(tmp_path):
    ch1 = tmp_path / "ch001.md"
    ch2 = tmp_path / "ch002.md"
    ch1.write_text("小九还活着，他说道。", encoding="utf-8")
    ch2.write_text("小九死了，化为星光消散。", encoding="utf-8")
    issues = check_character_consistency(str(tmp_path), (1, 2), ["小九"])
    alive_conflicts = [i for i in issues if i[0] == "ALIVE_CONFLICT"]
    assert alive_conflicts == []


def test_death_to_alive_flagged(tmp_path):
    ch1 = tmp_path / "ch001.md"
    ch2 = tmp_path / "ch002.md"
    ch1.write_text("小九死了，消散。", encoding="utf-8")
    ch2.write_text("小九还活着，他说。", encoding="utf-8")
    issues = check_character_consistency(str(tmp_path), (1, 2), ["小九"])
    assert any(i[0] == "ALIVE_CONFLICT" for i in issues)
