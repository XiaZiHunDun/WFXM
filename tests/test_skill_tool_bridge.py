"""Tests for butler.core.skill_tool_bridge."""

from butler.core.skill_tool_bridge import extract_skill_preferred_tools


class TestExtractSkillPreferredTools:
    def test_no_skill_section(self):
        result = extract_skill_preferred_tools("hello world")
        assert result == set()

    def test_empty_message(self):
        result = extract_skill_preferred_tools("")
        assert result == set()

    def test_skill_section_no_orchestrator(self):
        msg = "## 相关知识（Butler Skill）\n### `test-skill` (相关性 0.9)\nsome content"
        result = extract_skill_preferred_tools(msg)
        assert isinstance(result, set)
