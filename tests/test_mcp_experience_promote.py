"""E1/E2: experience MCP promote validation and same-turn merge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.mcp.deferred import (
    clear_promoted,
    merge_deferred_mcp_into_turn_tools,
    promote_experience_mcp_tools,
)


@pytest.fixture(autouse=True)
def _clear_promoted():
    clear_promoted("sess-promo")
    yield
    clear_promoted("sess-promo")


class TestPromoteExperienceMcpTools:
    def test_rejects_when_mcp_disabled(self, monkeypatch):
        monkeypatch.delenv("BUTLER_MCP_ENABLED", raising=False)
        monkeypatch.setenv("BUTLER_MCP_ENABLED", "0")
        added, rejected = promote_experience_mcp_tools(
            ["mcp_foo_bar"],
            session_key="sess-promo",
        )
        assert added == []
        assert rejected == [{"name": "mcp_foo_bar", "reason": "mcp_disabled"}]

    def test_rejects_unknown_tool_ref(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
        mgr = MagicMock()  # noqa: magicmock-no-spec
        mgr.get_tool_ref.return_value = None
        with (
            patch("butler.mcp.deferred._all_mcp_refs", return_value=[]),
            patch("butler.mcp.deferred.is_mcp_registered_name", return_value=True),
            patch("butler.mcp.manager.get_manager", return_value=mgr),
        ):
            added, rejected = promote_experience_mcp_tools(
                ["mcp_missing_tool"],
                session_key="sess-promo",
            )
        assert added == []
        assert rejected == [{"name": "mcp_missing_tool", "reason": "tool_not_found"}]

    def test_promotes_when_ref_exists(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
        ref = MagicMock()  # noqa: magicmock-no-spec
        mgr = MagicMock()  # noqa: magicmock-no-spec
        mgr.get_tool_ref.return_value = ref
        with (
            patch("butler.mcp.deferred._all_mcp_refs", return_value=[ref]),
            patch("butler.mcp.deferred.is_mcp_registered_name", return_value=True),
            patch("butler.mcp.manager.get_manager", return_value=mgr),
        ):
            added, rejected = promote_experience_mcp_tools(
                ["mcp_ok_tool"],
                session_key="sess-promo",
            )
        assert added == ["mcp_ok_tool"]
        assert rejected == []


class TestMergeDeferredMcpIntoTurnTools:
    def test_appends_only_new_defs(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
        monkeypatch.setenv("BUTLER_MCP_DEFERRED_TOOLS", "1")
        existing = [{"type": "function", "function": {"name": "read_file", "description": "r"}}]
        mcp_def = {"type": "function", "function": {"name": "mcp_new_tool", "description": "m"}}
        with patch(
            "butler.mcp.deferred.get_deferred_mcp_definitions",
            return_value=[mcp_def],
        ):
            merged = merge_deferred_mcp_into_turn_tools(existing, session_key="sess-promo")
        names = [t["function"]["name"] for t in merged]
        assert names == ["read_file", "mcp_new_tool"]


class TestAgentLoopSameTurn:
    def test_phase_enrich_same_turn_merge(self, monkeypatch):
        from butler.core.agent_loop_phases import _phase_enrich_user_text

        monkeypatch.setenv("BUTLER_MCP_DEFERRED_TOOLS", "1")
        monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
        monkeypatch.setenv("BUTLER_MCP_DEFERRED_SAME_TURN", "1")

        loop = MagicMock()  # noqa: magicmock-no-spec
        loop.tools = [{"function": {"name": "read_file", "description": "r"}}]
        loop.diagnostics = {}
        orch = MagicMock()  # noqa: magicmock-no-spec
        orch._skill_router = MagicMock()
        orch._skill_router.get_preferred_tools_for_names.return_value = set()

        mcp_def = {"function": {"name": "mcp_test_server_foo", "description": "t"}}

        with (
            patch(
                "butler.execution_context.get_current_orchestrator",
                return_value=orch,
            ),
            patch(
                "butler.session.memory_prefetch.peek_experience_hits",
                return_value=[{"content": "mcp:mcp_test_server_foo", "tags": ""}],
            ),
            patch(
                "butler.mcp.deferred.promote_experience_mcp_tools",
                return_value=(["mcp_test_server_foo"], []),
            ),
            patch(
                "butler.mcp.deferred.merge_deferred_mcp_into_turn_tools",
                return_value=[loop.tools[0], mcp_def],
            ) as merge,
            patch("butler.core.tool_selector.select_tools_for_context", side_effect=lambda tools, **kw: (tools, {})),
        ):
            turn_tools = _phase_enrich_user_text(loop, "发版", "sess-1")

        merge.assert_called_once()
        assert loop.diagnostics.get("experience_mcp_same_turn") == 1
        assert any(t.get("function", {}).get("name") == "mcp_test_server_foo" for t in turn_tools)
