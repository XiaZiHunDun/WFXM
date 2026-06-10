"""E3: structured skill header parsing for preferred_tools pin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from butler.core.skill_tool_bridge import (
    extract_injected_skill_names,
    extract_skill_preferred_tools,
)
from butler.skills.router import SkillRouter


class TestExtractInjectedSkillNames:
    def test_parses_headers_until_next_section(self):
        msg = (
            "## 相关知识（Butler Skill）\n"
            "### `alpha` (相关性 0.9)\n"
            "body a\n"
            "### `beta` (相关性 0.8)\n"
            "body b\n"
            "## 其他段落\n"
            "### `gamma`\n"
        )
        assert extract_injected_skill_names(msg) == ["alpha", "beta"]

    def test_no_section_returns_empty(self):
        assert extract_injected_skill_names("plain user text") == []


class TestExtractSkillPreferredToolsStructured:
    def test_uses_named_lookup_not_router_match(self):
        msg = (
            "## 相关知识（Butler Skill）\n"
            "### `target-skill` (相关性 0.9)\n"
            "unrelated keywords that would not route"
        )
        router = SkillRouter(
            [
                {
                    "name": "target-skill",
                    "description": "d",
                    "triggers": ["completely-different"],
                    "preferred_tools": ["run_workflow"],
                }
            ]
        )
        orch = MagicMock()  # noqa: magicmock-no-spec
        orch._skill_router = router
        with patch(
            "butler.execution_context.get_current_orchestrator",
            return_value=orch,
        ):
            tools = extract_skill_preferred_tools(msg)
        assert tools == {"run_workflow"}

    def test_router_match_not_called(self):
        msg = "## 相关知识\n### `x` (0.9)\nbody"
        router = SkillRouter(
            [
                {
                    "name": "x",
                    "description": "d",
                    "triggers": [],
                    "preferred_tools": ["read_file"],
                }
            ]
        )
        orch = MagicMock()  # noqa: magicmock-no-spec
        orch._skill_router = router
        with (
            patch(
                "butler.execution_context.get_current_orchestrator",
                return_value=orch,
            ),
            patch.object(router, "get_preferred_tools") as route_match,
            patch.object(router, "get_preferred_tools_for_names", wraps=router.get_preferred_tools_for_names) as by_name,
        ):
            extract_skill_preferred_tools(msg)
        route_match.assert_not_called()
        by_name.assert_called_once_with(["x"])
