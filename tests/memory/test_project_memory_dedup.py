import tempfile
from pathlib import Path

from butler.memory.project_memory import MarkdownMemory


def _count_lines(section: str, content: str) -> int:
    return sum(1 for line in section.splitlines() if content in line)


class TestMarkdownMemoryDedup:
    def test_repeated_fact_in_same_section_is_appended_once(self):
        with tempfile.TemporaryDirectory() as td:
            mm = MarkdownMemory(Path(td) / "MEMORY.md")

            mm.append("Architecture", "验收日：2026-07-10", classification="fact")
            mm.append("Architecture", "验收日：2026-07-10", classification="fact")

            assert _count_lines(mm.get_section("Architecture"), "验收日：2026-07-10") == 1

    def test_repeated_decision_is_appended_once(self):
        with tempfile.TemporaryDirectory() as td:
            mm = MarkdownMemory(Path(td) / "MEMORY.md")

            mm.append("Notes", "验收日：2026-07-10", classification="decision")
            mm.append("Notes", "验收日：2026-07-10", classification="decision")

            assert _count_lines(mm.get_section("Decisions"), "验收日：2026-07-10") == 1

    def test_whitespace_variant_is_treated_as_same_content(self):
        with tempfile.TemporaryDirectory() as td:
            mm = MarkdownMemory(Path(td) / "MEMORY.md")

            mm.append("Architecture", "验收日：2026-07-10", classification="fact")
            mm.append("Architecture", "  验收日：2026-07-10  ", classification="fact")

            assert _count_lines(mm.get_section("Architecture"), "验收日：2026-07-10") == 1

    def test_same_content_in_different_sections_is_kept(self):
        with tempfile.TemporaryDirectory() as td:
            mm = MarkdownMemory(Path(td) / "MEMORY.md")

            mm.append("Architecture", "验收日：2026-07-10", classification="fact")
            mm.append("Notes", "验收日：2026-07-10", classification="fact")

            assert _count_lines(mm.get_section("Architecture"), "验收日：2026-07-10") == 1
            assert _count_lines(mm.get_section("Notes"), "验收日：2026-07-10") == 1

    def test_different_content_in_same_section_is_kept(self):
        with tempfile.TemporaryDirectory() as td:
            mm = MarkdownMemory(Path(td) / "MEMORY.md")

            mm.append("Architecture", "验收日：2026-07-10", classification="fact")
            mm.append("Architecture", "验收范围：P1 #6", classification="fact")

            section = mm.get_section("Architecture")
            assert "验收日：2026-07-10" in section
            assert "验收范围：P1 #6" in section

    def test_empty_content_is_not_appended(self):
        with tempfile.TemporaryDirectory() as td:
            mm = MarkdownMemory(Path(td) / "MEMORY.md")

            mm.append("Notes", "   ", classification="fact")

            assert mm.get_section("Notes") == ""

    def test_approve_pending_does_not_duplicate_existing_target_bullet(self):
        with tempfile.TemporaryDirectory() as td:
            mm = MarkdownMemory(Path(td) / "MEMORY.md")

            mm.append("Decisions", "验收日：2026-07-10", classification="decision")
            mm.append("Decisions", "验收日：2026-07-10", classification="pending")

            assert mm.approve_pending(0) is True
            assert _count_lines(mm.get_section("Decisions"), "验收日：2026-07-10") == 1
            assert mm.list_pending() == []

    def test_approve_all_repeated_pending_items_write_one_target_bullet(self):
        with tempfile.TemporaryDirectory() as td:
            mm = MarkdownMemory(Path(td) / "MEMORY.md")

            mm.append("Decisions", "验收日：2026-07-10", classification="pending")
            mm.append("Decisions", "验收日：2026-07-10", classification="pending")

            assert mm.approve_all() == 2
            assert _count_lines(mm.get_section("Decisions"), "验收日：2026-07-10") == 1
            assert mm.list_pending() == []
