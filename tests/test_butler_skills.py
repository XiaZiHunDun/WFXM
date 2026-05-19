"""Tests for butler.skills — SkillManager, SkillSimilarity, SkillConsolidator, SkillRouter."""

import tempfile
from pathlib import Path

import pytest

from butler.skills.consolidator import SkillConsolidator
from butler.skills.manager import SkillManager
from butler.skills.router import SkillRouter
from butler.skills.similarity import SkillSimilarity, trigger_jaccard, tfidf_cosine
from butler.skills.usage import UsageTracker


class TestSimilarity:
    def test_jaccard_identical(self):
        assert trigger_jaccard(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_jaccard_disjoint(self):
        assert trigger_jaccard(["a", "b"], ["c", "d"]) == 0.0

    def test_jaccard_partial(self):
        score = trigger_jaccard(["python", "test", "debug"], ["python", "test", "deploy"])
        assert 0.3 < score < 0.8

    def test_tfidf_similar(self):
        score = tfidf_cosine("python web development flask", "python web framework django")
        assert score > 0.3

    def test_tfidf_dissimilar(self):
        score = tfidf_cosine("cooking recipes pasta", "quantum physics entanglement")
        assert score < 0.3

    def test_skill_similarity_find(self):
        existing = [
            {"name": "python-debug", "description": "Debug Python code", "triggers": ["python", "debug", "error"]},
            {"name": "git-workflow", "description": "Git workflow management", "triggers": ["git", "commit", "branch"]},
        ]
        sim = SkillSimilarity()
        new_skill = {"name": "py-troubleshoot", "description": "Troubleshoot Python errors", "triggers": ["python", "error", "fix"]}
        matches = sim.find_similar(new_skill, existing, threshold=0.3)
        assert len(matches) >= 1
        assert matches[0][0]["name"] == "python-debug"


class TestConsolidator:
    def test_single_skill_passthrough(self):
        cons = SkillConsolidator()
        skill = {"name": "test", "description": "desc", "triggers": ["t1"], "content": "body"}
        result = cons.consolidate([skill])
        assert result["name"] == "test"

    def test_deterministic_merge_no_llm(self):
        cons = SkillConsolidator()
        skills = [
            {"name": "a", "description": "Skill A", "triggers": ["x", "y"], "content": "Body A"},
            {"name": "b", "description": "Skill B", "triggers": ["y", "z"], "content": "Body B"},
        ]
        merged = cons.consolidate(skills)
        assert "x" in merged.get("triggers", [])
        assert "z" in merged.get("triggers", [])
        content = merged.get("content", "")
        assert "Body A" in content
        assert "Body B" in content


class TestRouter:
    def test_match_by_trigger(self):
        skills = [
            {"name": "python-dev", "description": "Python development", "triggers": ["python", "pip"], "content": "Use pytest"},
            {"name": "docker-ops", "description": "Docker operations", "triggers": ["docker", "container"], "content": "Use docker-compose"},
        ]
        router = SkillRouter(skills)
        matches = router.match("I need to run python tests")
        assert len(matches) >= 1
        assert matches[0]["name"] == "python-dev"

    def test_match_empty_query(self):
        router = SkillRouter([])
        matches = router.match("")
        assert matches == []

    def test_match_top_k(self):
        skills = [
            {"name": f"skill-{i}", "description": f"Skill {i}", "triggers": [f"trigger{i}", "common"], "content": f"body {i}"}
            for i in range(10)
        ]
        router = SkillRouter(skills)
        matches = router.match("common trigger", top_k=3)
        assert len(matches) <= 3


class TestSkillManager:
    def test_create_and_list(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = SkillManager(td)
            result = mgr.create("test-skill", "A test skill", ["test", "debug"], "Test content")
            assert result == "created"
            skills = mgr.list_skills()
            assert len(skills) == 1
            assert skills[0]["name"] == "test-skill"

    def test_get_skill(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = SkillManager(td)
            mgr.create("my-skill", "My skill", ["key"], "Full body here")
            skill = mgr.get_skill("my-skill")
            assert skill is not None
            assert skill["content"] == "Full body here"

    def test_edit_skill(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = SkillManager(td)
            mgr.create("editable", "Editable skill", ["edit"], "Original content")
            mgr.edit("editable", "Updated content")
            skill = mgr.get_skill("editable")
            assert skill["content"] == "Updated content"

    def test_delete_skill(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = SkillManager(td)
            mgr.create("deletable", "To delete", ["del"], "Will be deleted")
            mgr.delete("deletable")
            assert mgr.get_skill("deletable") is None

    def test_global_and_project_skills(self):
        with tempfile.TemporaryDirectory() as td:
            global_dir = Path(td) / "global"
            global_dir.mkdir()
            proj_dir = Path(td) / "project"
            proj_dir.mkdir()
            mgr_global = SkillManager(global_dir)
            mgr_global.create("shared", "Shared skill", ["share"], "Global version")

            mgr = SkillManager(proj_dir, global_skills_dir=global_dir)
            skills = mgr.list_skills()
            assert any(s["name"] == "shared" for s in skills)


class TestUsageTracker:
    def test_tracking(self):
        with tempfile.TemporaryDirectory() as td:
            tracker = UsageTracker(Path(td) / ".butler_skill_usage.json")
            tracker.on_create("skill-a")
            tracker.on_view("skill-a")
            tracker.on_use("skill-a")
            stats = tracker.get_stats("skill-a")
            assert stats["views"] >= 1
            assert stats["uses"] >= 1

    def test_merge_tracking(self):
        with tempfile.TemporaryDirectory() as td:
            tracker = UsageTracker(Path(td) / ".butler_skill_usage.json")
            tracker.on_create("old-1")
            tracker.on_create("old-2")
            tracker.on_merge(["old-1", "old-2"], "merged")
            stats = tracker.get_stats("merged")
            assert stats is not None


@pytest.mark.module_test
class TestSkillManagerMergePath:
    def test_two_similar_skills_second_triggers_merge(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = SkillManager(td, llm_fn=None)
            mgr.create(
                "python-debug",
                "Debug Python applications",
                ["python", "debug", "error", "traceback"],
                "Step 1: read traceback\nStep 2: fix",
            )
            result = mgr.create(
                "python-troubleshoot",
                "Troubleshoot Python errors and exceptions",
                ["python", "error", "fix", "debug"],
                "Step 1: reproduce\nStep 2: patch",
                similarity_threshold=0.3,
            )
            assert result == "merged"
            skills = mgr.list_skills()
            assert len(skills) == 1

    def test_validate_name_invalid_characters_raises(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = SkillManager(td)
            with pytest.raises(ValueError, match="Invalid skill name"):
                mgr.create("Bad Name!", "desc", ["t"], "body")

    def test_empty_description_raises(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = SkillManager(td)
            with pytest.raises(ValueError, match="Description is required"):
                mgr.create("valid-name", "", ["t"], "body")

    def test_empty_content_raises(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = SkillManager(td)
            with pytest.raises(ValueError, match="Content is required"):
                mgr.create("valid-name", "desc", ["t"], "   ")


@pytest.mark.module_test
class TestConsolidatorWithLLM:
    def test_mock_llm_returns_merged_content(self):
        def llm_fn(prompt):
            return (
                '{"name": "merged-skill", "description": "Merged", '
                '"triggers": ["a", "b"], "content": "# Merged workflow"}'
            )

        cons = SkillConsolidator(llm_fn=llm_fn)
        skills = [
            {"name": "a", "description": "A", "triggers": ["a"], "content": "Body A"},
            {"name": "b", "description": "B", "triggers": ["b"], "content": "Body B"},
        ]
        merged = cons.consolidate(skills)
        assert merged["name"] == "merged-skill"
        assert merged["content"] == "# Merged workflow"
        assert set(merged["triggers"]) == {"a", "b"}

    def test_fallback_when_llm_fails(self):
        def llm_fn(prompt):
            raise RuntimeError("llm unavailable")

        cons = SkillConsolidator(llm_fn=llm_fn)
        skills = [
            {"name": "x", "description": "X", "triggers": ["t1"], "content": "Body X"},
            {"name": "y", "description": "Y", "triggers": ["t2"], "content": "Body Y"},
        ]
        merged = cons.consolidate(skills)
        assert merged["name"] == "x-merged"
        assert "Body X" in merged["content"]
        assert "Body Y" in merged["content"]
        assert "t1" in merged["triggers"] and "t2" in merged["triggers"]
