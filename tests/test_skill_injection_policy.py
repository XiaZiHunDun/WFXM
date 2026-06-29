"""Skill injection policy: experience-first, skill fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.skills.injection_policy import (
    extract_skill_refs_from_hits,
    resolve_skill_injection,
)


class TestExtractSkillRefs:
    def test_from_tags_and_content(self):
        hits = [
            {"tags": "skill:memory-ops,note", "content": "see skill:phase-c too"},
        ]
        assert extract_skill_refs_from_hits(hits) == ["memory-ops", "phase-c"]


class TestResolveSkillInjection:
    def test_fallback_skips_when_experience_hits(self, monkeypatch):
        monkeypatch.setenv("BUTLER_SKILL_INJECTION_MODE", "fallback")
        monkeypatch.setenv("BUTLER_SKILL_FALLBACK_MIN_EXPERIENCE_HITS", "1")
        orch = MagicMock()  # noqa: magicmock-no-spec
        with patch(
            "butler.session.memory_prefetch.peek_experience_hits",
            return_value=[{"id": 1, "content": "已知流程", "tags": ""}],
        ):
            d = resolve_skill_injection(orch, "发版流程", diagnostics={})
        assert d.skip is True
        assert d.reason == "experience_hit_skip_unverified_skill"

    def test_fallback_loads_refs_when_present(self, monkeypatch):
        monkeypatch.setenv("BUTLER_SKILL_INJECTION_MODE", "fallback")
        hits = [{"content": "用 skill:webnovel-write", "tags": ""}]
        with patch(
            "butler.session.memory_prefetch.peek_experience_hits",
            return_value=hits,
        ):
            d = resolve_skill_injection(MagicMock(), "写章", diagnostics={})  # noqa: magicmock-no-spec
        assert d.skip is False
        assert d.skill_names == ("webnovel-write",)

    def test_always_never_skips(self, monkeypatch):
        monkeypatch.setenv("BUTLER_SKILL_INJECTION_MODE", "always")
        with patch(
            "butler.session.memory_prefetch.peek_experience_hits",
            return_value=[{"content": "x"}],
        ):
            d = resolve_skill_injection(MagicMock(), "q", diagnostics={})  # noqa: magicmock-no-spec
        assert d.skip is False
        assert d.reason == "always"

    def test_records_fallback_skip_metric(self, monkeypatch):
        from butler.ops import runtime_metrics as rm

        monkeypatch.setenv("BUTLER_SKILL_INJECTION_MODE", "fallback")
        rm.reset_global()
        with patch(
            "butler.session.memory_prefetch.peek_experience_hits",
            return_value=[{"content": "known", "tags": ""}],
        ):
            resolve_skill_injection(MagicMock(), "q", diagnostics={})  # noqa: magicmock-no-spec
        snap = rm.snapshot_global()
        assert snap["counters"].get("execution_fallback_skip") == 1


@pytest.mark.integration
class TestOrchestratorSkillInjectionPolicy:
    def test_inject_skipped_when_experience_covers(
        self, monkeypatch, butler_orchestrator
    ):
        monkeypatch.setenv("BUTLER_SKILL_INJECTION_MODE", "fallback")
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "0")
        butler_orchestrator.butler_memory.add_experience(
            "p",
            "note",
            "发版必须先跑 butler-memory-phase-c 守门",
        )

        manager = MagicMock()  # noqa: magicmock-no-spec
        manager.list_skills.return_value = [
            {
                "name": "python-dev",
                "description": "py",
                "triggers": ["python"],
                "content": "SKILL BODY",
            },
        ]
        with (
            patch(
                "butler.session.memory_prefetch.peek_experience_hits",
                return_value=[
                    {
                        "content": "发版必须先跑 butler-memory-phase-c 守门",
                        "tags": "",
                    }
                ],
            ),
            patch("butler.orchestrator.templates.combined_skill_manager", return_value=manager),
        ):
            butler_orchestrator._rebuild_skill_router()

            diagnostics: dict = {}
            out = butler_orchestrator.inject_skill_context(
                "发版守门 butler-memory-phase-c",
                diagnostics=diagnostics,
            )
        assert out == "发版守门 butler-memory-phase-c"
        assert diagnostics.get("skill_context_injected") is False
        assert diagnostics.get("skill_injection_reason") == (
            "experience_hit_skip_unverified_skill"
        )

    def test_inject_named_skill_from_experience_ref(
        self, monkeypatch, butler_orchestrator
    ):
        monkeypatch.setenv("BUTLER_SKILL_INJECTION_MODE", "fallback")
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "0")
        butler_orchestrator.butler_memory.add_experience(
            "p",
            "note",
            "章节写作请用 skill:chapter-draft",
            tags="skill:chapter-draft",
        )

        manager = MagicMock()  # noqa: magicmock-no-spec
        manager.list_skills.return_value = [
            {"name": "chapter-draft", "description": "d", "triggers": []},
        ]
        manager.get_skills.return_value = {
            "chapter-draft": {
                "name": "chapter-draft",
                "content": "Draft steps here",
            },
        }
        with (
            patch(
                "butler.session.memory_prefetch.peek_experience_hits",
                return_value=[
                    {
                        "content": "章节写作请用 skill:chapter-draft",
                        "tags": "skill:chapter-draft",
                    }
                ],
            ),
            patch("butler.orchestrator.templates.combined_skill_manager", return_value=manager),
        ):
            butler_orchestrator._rebuild_skill_router()

            out = butler_orchestrator.inject_skill_context("写下一章")
        assert "Draft steps here" in out
        manager.get_skills.assert_called_once()
