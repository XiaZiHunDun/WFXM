"""Execution trust cascade: experience tool:/skill:/mcp: pins."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.core.skill_tool_bridge import (
    collect_pinned_tools,
    resolve_experience_pinned_tools,
)
from butler.memory.embedding import HashingEmbedder
from butler.memory.semantic_index import (
    SOURCE_EXPERIENCE,
    SOURCE_OWNER_PROFILE,
    SemanticMemoryIndex,
    enrich_experience_hit_tags,
    filter_experience_hits,
    hybrid_experience_search,
)
from butler.skills.experience_pointers import (
    extract_mcp_refs_from_hits,
    extract_tool_refs_from_hits,
    resolve_mcp_refs_to_registered,
)
from butler.skills.router import SkillRouter


class TestExperienceHitEnrichment:
    def test_filter_drops_owner_profile_vector_hits(self):
        hits = [
            {"source": SOURCE_OWNER_PROFILE, "source_id": "entry:5", "content": "profile"},
            {"source": SOURCE_EXPERIENCE, "source_id": "218", "content": "发版流程"},
            {"id": 219, "content": "fts row"},
        ]
        out = filter_experience_hits(hits)
        assert len(out) == 2
        assert all(h.get("source") != SOURCE_OWNER_PROFILE for h in out)

    def test_enrich_fills_tags_from_store(self):
        store = MagicMock()  # noqa: magicmock-no-spec
        store.fetch_by_ids.return_value = [
            {"id": 218, "tags": "tool:butler_recall,skill:phase-c"},
        ]
        hits = [
            {"source": SOURCE_EXPERIENCE, "source_id": "218", "content": "发版", "tags": ""},
        ]
        out = enrich_experience_hit_tags(hits, store)
        assert out[0]["tags"] == "tool:butler_recall,skill:phase-c"
        assert out[0]["id"] == 218
        store.fetch_by_ids.assert_called_once_with([218])

    def test_hybrid_experience_search_pins_tools_after_enrich(self, tmp_path):
        idx = SemanticMemoryIndex(tmp_path / "vec.db", HashingEmbedder(dimension=64))
        idx.upsert(
            source=SOURCE_EXPERIENCE,
            source_id="42",
            content="记忆模块发版流程 butler_recall",
            project="",
            category="ops",
        )
        idx.upsert(
            source=SOURCE_OWNER_PROFILE,
            source_id="entry:9",
            content="owner 偏好 记忆模块发版流程",
            project="",
            category="profile",
        )

        store = MagicMock()  # noqa: magicmock-no-spec
        store.fetch_by_ids.return_value = [
            {"id": 42, "tags": "tool:butler_recall,skill:butler-memory-phase-c"},
        ]

        def fts_search(_q: str, *, project=None, limit=8):
            return []

        out = hybrid_experience_search(
            idx,
            fts_search,
            "记忆模块发版流程",
            limit=5,
            experience_store=store,
        )
        assert out
        assert all(h.get("source") != SOURCE_OWNER_PROFILE for h in out)
        assert any("tool:butler_recall" in str(h.get("tags") or "") for h in out)
        refs = extract_tool_refs_from_hits(out)
        assert "butler_recall" in refs


class TestExperiencePointerParsing:
    def test_tool_refs(self):
        hits = [{"tags": "tool:run_workflow,note", "content": "also tool:memo_add"}]
        assert extract_tool_refs_from_hits(hits) == ["run_workflow", "memo_add"]

    def test_mcp_refs_registered_and_slash(self):
        hits = [
            {
                "content": "use mcp:mcp_github_search and mcp:github/create_issue",
                "tags": "",
            }
        ]
        assert extract_mcp_refs_from_hits(hits) == [
            "mcp_github_search",
            "github/create_issue",
        ]

    def test_resolve_mcp_refs(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MCP_TOOL_PREFIX", "mcp")
        assert resolve_mcp_refs_to_registered(["mcp_github_search"]) == [
            "mcp_github_search"
        ]
        assert resolve_mcp_refs_to_registered(["github/create_issue"]) == [
            "mcp_github_create_issue"
        ]


class TestSkillRouterPreferredByName:
    def test_get_preferred_tools_for_names(self):
        router = SkillRouter(
            [
                {
                    "name": "webnovel-write",
                    "description": "write",
                    "triggers": [],
                    "preferred_tools": ["read_file", "write_file"],
                },
                {
                    "name": "other",
                    "description": "x",
                    "triggers": [],
                    "preferred_tools": ["terminal"],
                },
            ]
        )
        assert router.get_preferred_tools_for_names(["webnovel-write"]) == {
            "read_file",
            "write_file",
        }


class TestResolveExperiencePinnedTools:
    def test_pins_tools_and_skill_preferred_without_body(self):
        orch = MagicMock()  # noqa: magicmock-no-spec
        orch._skill_router = SkillRouter(
            [
                {
                    "name": "phase-c",
                    "description": "c",
                    "triggers": [],
                    "preferred_tools": ["run_workflow"],
                }
            ]
        )
        hits = [
            {
                "content": "流程 skill:phase-c tool:memo_add",
                "tags": "mcp:github/search",
            }
        ]
        with (
            patch(
                "butler.execution_context.get_current_orchestrator",
                return_value=orch,
            ),
            patch(
                "butler.session.memory_prefetch.peek_experience_hits",
                return_value=hits,
            ),
        ):
            builtin, mcp = resolve_experience_pinned_tools("发版流程")
        assert "memo_add" in builtin
        assert "run_workflow" in builtin
        assert "mcp_github_search" in mcp

    def test_no_orchestrator_returns_empty(self):
        with patch(
            "butler.execution_context.get_current_orchestrator",
            return_value=None,
        ):
            builtin, mcp = resolve_experience_pinned_tools("q")
        assert builtin == set()
        assert mcp == []


class TestCollectPinnedTools:
    def test_merges_injected_and_experience_pins(self):
        msg = "## 相关知识（Butler Skill）\n### `x` (相关性 0.9)\nbody"
        orch = MagicMock()  # noqa: magicmock-no-spec
        orch._skill_router = SkillRouter(
            [
                {
                    "name": "x",
                    "description": "d",
                    "triggers": ["x"],
                    "preferred_tools": ["read_file"],
                }
            ]
        )
        with (
            patch(
                "butler.execution_context.get_current_orchestrator",
                return_value=orch,
            ),
            patch(
                "butler.session.memory_prefetch.peek_experience_hits",
                return_value=[{"content": "tool:butler_recall", "tags": ""}],
            ),
        ):
            builtin, mcp = collect_pinned_tools(msg)
        assert "read_file" in builtin
        assert "butler_recall" in builtin
        assert mcp == []


@pytest.mark.integration
class TestAgentLoopExperienceMcpPromote:
    def test_phase_enrich_promotes_experience_mcp(self, monkeypatch):
        from butler.core.agent_loop_phases import _phase_enrich_user_text

        monkeypatch.setenv("BUTLER_MCP_DEFERRED_TOOLS", "1")
        monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")

        loop = MagicMock()  # noqa: magicmock-no-spec
        loop.tools = [{"function": {"name": "read_file", "description": "r"}}]
        loop.diagnostics = {}

        orch = MagicMock()  # noqa: magicmock-no-spec
        orch._skill_router = SkillRouter([])

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
                "butler.mcp.naming.is_mcp_registered_name",
                return_value=True,
            ),
            patch(
                "butler.mcp.deferred.promote_experience_mcp_tools",
                return_value=(["mcp_test_server_foo"], []),
            ) as promote,
        ):
            _phase_enrich_user_text(loop, "发版", "sess-1")

        promote.assert_called_once()
        assert loop.diagnostics.get("experience_mcp_promoted") == 1
