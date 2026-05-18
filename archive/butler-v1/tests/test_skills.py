"""Tests for the Skill system (loader, similarity, router, consolidator, manager, usage)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from butler.skills.loader import SkillLoader, _parse_yaml_frontmatter
from butler.skills.similarity import (
    SkillSimilarity,
    trigger_jaccard,
    tfidf_cosine,
)
from butler.skills.router import SkillRouter
from butler.skills.consolidator import SkillConsolidator
from butler.skills.manager import SkillManager
from butler.skills.usage import UsageTracker


def _create_skill_dir(base: Path, name: str, meta: dict, body: str) -> Path:
    """Helper to create a SKILL.md file in a subdirectory."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f'  - "{item}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return skill_dir


class TestYAMLFrontmatter:
    def test_basic_parsing(self):
        text = '---\nname: test-skill\ndescription: A test skill\n---\nBody content here'
        meta, body = _parse_yaml_frontmatter(text)
        assert meta["name"] == "test-skill"
        assert meta["description"] == "A test skill"
        assert body == "Body content here"

    def test_list_parsing(self):
        text = '---\nname: test\ntriggers:\n  - "keyword1"\n  - "keyword2"\n---\nBody'
        meta, body = _parse_yaml_frontmatter(text)
        assert meta["triggers"] == ["keyword1", "keyword2"]

    def test_no_frontmatter(self):
        text = "Just plain text"
        meta, body = _parse_yaml_frontmatter(text)
        assert meta == {}
        assert body == "Just plain text"


class TestSkillLoader:
    def test_dual_directory_loading(self, tmp_dir):
        global_dir = tmp_dir / "global_skills"
        project_dir = tmp_dir / "project_skills"

        _create_skill_dir(global_dir, "global-skill", {
            "name": "global-skill",
            "description": "全局技能",
            "triggers": ["global"],
            "scope": "global",
        }, "全局技能内容")

        _create_skill_dir(project_dir, "project-skill", {
            "name": "project-skill",
            "description": "项目技能",
            "triggers": ["project"],
            "scope": "project",
        }, "项目技能内容")

        loader = SkillLoader(project_skills_dir=project_dir, global_skills_dir=global_dir)
        all_skills = loader.list_skills(scope="all")
        assert len(all_skills) == 2

        global_skills = loader.list_skills(scope="global")
        assert len(global_skills) == 1
        assert global_skills[0].name == "global-skill"

        project_skills = loader.list_skills(scope="project")
        assert len(project_skills) == 1
        assert project_skills[0].name == "project-skill"

    def test_skill_names(self, tmp_dir):
        skill_dir = tmp_dir / "skills"
        _create_skill_dir(skill_dir, "skill-a", {
            "name": "skill-a", "description": "A"}, "Body A")
        _create_skill_dir(skill_dir, "skill-b", {
            "name": "skill-b", "description": "B"}, "Body B")

        loader = SkillLoader(project_skills_dir=skill_dir)
        names = loader.skill_names()
        assert sorted(names) == ["skill-a", "skill-b"]

    def test_get_skill(self, tmp_dir):
        skill_dir = tmp_dir / "skills"
        _create_skill_dir(skill_dir, "my-skill", {
            "name": "my-skill",
            "description": "测试技能",
            "triggers": ["test", "debug"],
            "tools": ["read_file", "write_file"],
        }, "详细的技能步骤说明")

        loader = SkillLoader(project_skills_dir=skill_dir)
        skill = loader.get_skill("my-skill")
        assert skill is not None
        assert skill.description == "测试技能"
        assert skill.triggers == ["test", "debug"]
        assert skill.tools == ["read_file", "write_file"]
        assert "详细的技能步骤" in skill.body

    def test_empty_directory(self, tmp_dir):
        loader = SkillLoader(project_skills_dir=tmp_dir / "nonexistent")
        assert loader.list_skills() == []

    def test_build_skill_summary(self, tmp_dir):
        skill_dir = tmp_dir / "skills"
        _create_skill_dir(skill_dir, "deploy", {
            "name": "deploy",
            "description": "部署应用",
            "triggers": ["deploy", "发布"],
        }, "部署步骤")

        loader = SkillLoader(project_skills_dir=skill_dir)
        summary = loader.build_skill_summary()
        assert "deploy" in summary
        assert "部署应用" in summary


class TestTriggerJaccard:
    def test_identical(self):
        assert trigger_jaccard(["a", "b"], ["a", "b"]) == 1.0

    def test_disjoint(self):
        assert trigger_jaccard(["a", "b"], ["c", "d"]) == 0.0

    def test_partial_overlap(self):
        score = trigger_jaccard(["a", "b", "c"], ["b", "c", "d"])
        assert 0.4 < score < 0.6  # 2/4 = 0.5

    def test_empty_triggers(self):
        assert trigger_jaccard([], ["a"]) == 0.0

    def test_case_insensitive(self):
        assert trigger_jaccard(["Debug"], ["debug"]) == 1.0


class TestTFIDFCosine:
    def test_identical_text(self):
        score = tfidf_cosine("Python programming", "Python programming")
        assert score > 0.9

    def test_similar_text(self):
        score = tfidf_cosine(
            "Python web development with Flask",
            "Python web framework Flask application",
        )
        assert score > 0.3

    def test_unrelated_text(self):
        score = tfidf_cosine(
            "Machine learning algorithms",
            "Cooking recipes for dinner",
        )
        assert score < 0.2

    def test_empty_text(self):
        assert tfidf_cosine("", "some text") == 0.0
        assert tfidf_cosine("", "") == 0.0

    def test_chinese_text(self):
        score = tfidf_cosine(
            "Python 项目部署和运维",
            "Python 服务部署与运维管理",
        )
        assert score > 0.2


class TestSkillRouter:
    def _make_skills(self, tmp_dir) -> list:
        from butler.skills.loader import SkillInfo
        return [
            SkillInfo(
                name="deploy-skill",
                description="自动化部署流程",
                triggers=["deploy", "发布", "部署"],
                body="使用 Docker 和 K8s 部署应用",
            ),
            SkillInfo(
                name="debug-skill",
                description="调试问题的技巧",
                triggers=["debug", "调试", "bug"],
                body="使用日志和断点调试",
            ),
            SkillInfo(
                name="review-skill",
                description="代码审查流程",
                triggers=["review", "审查", "code review"],
                body="检查代码质量和规范",
            ),
        ]

    def test_trigger_match(self, tmp_dir):
        router = SkillRouter()
        skills = self._make_skills(tmp_dir)
        matched = router.match("帮我部署这个应用", skills)
        assert len(matched) >= 1
        assert matched[0].name == "deploy-skill"

    def test_no_match(self, tmp_dir):
        router = SkillRouter()
        skills = self._make_skills(tmp_dir)
        matched = router.match("今天天气怎么样", skills)
        assert len(matched) == 0

    def test_top_k(self, tmp_dir):
        router = SkillRouter()
        skills = self._make_skills(tmp_dir)
        matched = router.match("部署后调试问题", skills, top_k=2)
        assert len(matched) <= 2

    def test_empty_input(self, tmp_dir):
        router = SkillRouter()
        matched = router.match("", self._make_skills(tmp_dir))
        assert matched == []

    def test_empty_skills(self):
        router = SkillRouter()
        matched = router.match("deploy something", [])
        assert matched == []


class TestSkillSimilarity:
    def test_no_existing_skills(self):
        sim = SkillSimilarity()
        results = asyncio.run(
            sim.find_similar({"name": "new", "triggers": ["test"]}, [])
        )
        assert results == []

    def test_trigger_overlap_detection(self):
        sim = SkillSimilarity(trigger_threshold=0.3)
        new_skill = {"name": "new-deploy", "triggers": ["deploy", "发布"], "description": "", "body": ""}
        existing = [
            {"name": "old-deploy", "triggers": ["deploy", "部署", "发布"], "description": "", "body": ""},
            {"name": "unrelated", "triggers": ["cooking", "recipe"], "description": "", "body": ""},
        ]
        results = asyncio.run(
            sim.find_similar(new_skill, existing)
        )
        assert len(results) >= 1
        assert results[0].skill_name == "old-deploy"
        assert results[0].pre_method == "trigger_jaccard"

    def test_tfidf_detection(self):
        sim = SkillSimilarity(trigger_threshold=0.9, tfidf_threshold=0.3)
        new_skill = {
            "name": "python-deploy",
            "triggers": [],
            "description": "Python 应用部署自动化流程",
            "body": "使用 Docker 容器化 Python 应用并部署到 K8s",
        }
        existing = [
            {
                "name": "docker-deploy",
                "triggers": [],
                "description": "Docker 容器部署流程",
                "body": "容器化应用 Docker 构建并部署到 Kubernetes",
            },
        ]
        results = asyncio.run(
            sim.find_similar(new_skill, existing)
        )
        assert len(results) >= 1
        assert results[0].pre_method == "tfidf_cosine"


class TestSkillConsolidator:
    def test_single_skill_passthrough(self):
        consolidator = SkillConsolidator()
        skill = {"name": "solo", "description": "单一技能", "body": "内容"}
        result = asyncio.run(consolidator.merge([skill]))
        assert result.success
        assert result.merged_skill == skill

    def test_empty_skills(self):
        consolidator = SkillConsolidator()
        result = asyncio.run(consolidator.merge([]))
        assert not result.success

    def test_merge_requires_llm(self):
        consolidator = SkillConsolidator(llm_call=None)
        skills = [
            {"name": "a", "description": "A", "triggers": ["x"], "body": "body A"},
            {"name": "b", "description": "B", "triggers": ["y"], "body": "body B"},
        ]
        result = asyncio.run(consolidator.merge(skills))
        assert not result.success
        assert "LLM" in result.error

    def test_merge_with_mock_llm(self):
        async def mock_llm(prompt: str) -> str:
            return json.dumps({
                "name": "merged-skill",
                "description": "合并后的技能",
                "triggers": ["x", "y"],
                "tools": [],
                "body": "合并内容",
            })

        consolidator = SkillConsolidator(llm_call=mock_llm)
        skills = [
            {"name": "a", "description": "A", "triggers": ["x"], "body": "body A"},
            {"name": "b", "description": "B", "triggers": ["y"], "body": "body B"},
        ]
        result = asyncio.run(consolidator.merge(skills))
        assert result.success
        assert result.merged_skill["name"] == "merged-skill"
        assert result.old_names == ["a", "b"]


class TestSkillManager:
    def _make_manager(self, tmp_dir):
        project_dir = tmp_dir / "skills"
        project_dir.mkdir()
        loader = SkillLoader(project_skills_dir=project_dir)
        sim = SkillSimilarity(trigger_threshold=0.3, tfidf_threshold=0.5)
        consolidator = SkillConsolidator()
        usage = UsageTracker(tmp_dir / ".usage.json")
        return SkillManager(loader, sim, consolidator, usage), project_dir

    def test_create_standalone(self, tmp_dir):
        mgr, skill_dir = self._make_manager(tmp_dir)
        result = asyncio.run(
            mgr.create("test-skill", "测试技能", ["test"], ["read_file"], "技能步骤", scope="project")
        )
        assert result["success"]
        assert result["action"] == "created"
        assert (skill_dir / "test_skill" / "SKILL.md").exists()

    def test_create_invalid_name(self, tmp_dir):
        mgr, _ = self._make_manager(tmp_dir)
        result = asyncio.run(
            mgr.create("Invalid Name!", "desc", [], [], "body")
        )
        assert not result["success"]

    def test_create_missing_description(self, tmp_dir):
        mgr, _ = self._make_manager(tmp_dir)
        result = asyncio.run(
            mgr.create("valid-name", "", [], [], "body")
        )
        assert not result["success"]

    def test_create_duplicate(self, tmp_dir):
        mgr, _ = self._make_manager(tmp_dir)
        asyncio.run(
            mgr.create("dup-skill", "描述", ["t"], [], "内容")
        )
        result = asyncio.run(
            mgr.create("dup-skill", "描述2", ["t2"], [], "内容2")
        )
        assert not result["success"]
        assert "already exists" in result["error"]

    def test_edit(self, tmp_dir):
        mgr, _ = self._make_manager(tmp_dir)
        asyncio.run(
            mgr.create("edit-me", "旧描述", ["old"], [], "旧内容")
        )
        result = asyncio.run(
            mgr.edit("edit-me", description="新描述", body="新内容")
        )
        assert result["success"]
        skill = mgr._loader.get_skill("edit-me")
        assert skill.description == "新描述"
        assert "新内容" in skill.body

    def test_delete(self, tmp_dir):
        mgr, skill_dir = self._make_manager(tmp_dir)
        asyncio.run(
            mgr.create("delete-me", "删除测试", ["del"], [], "内容")
        )
        result = asyncio.run(mgr.delete("delete-me"))
        assert result["success"]
        assert mgr._loader.get_skill("delete-me") is None
        assert (skill_dir / ".archive").exists()

    def test_create_with_auto_merge(self, tmp_dir):
        async def mock_llm(prompt: str) -> str:
            if "相似度判定" in prompt or "Skill A" in prompt:
                return json.dumps({
                    "similar": True, "confidence": 0.9,
                    "reason": "Both are deployment skills",
                    "merge_suggestion": "merged-deploy",
                })
            else:
                return json.dumps({
                    "name": "merged-deploy",
                    "description": "统一部署技能",
                    "triggers": ["deploy", "部署", "docker", "k8s"],
                    "tools": [],
                    "body": "合并后的部署流程",
                })

        project_dir = tmp_dir / "skills"
        project_dir.mkdir()
        loader = SkillLoader(project_skills_dir=project_dir)
        sim = SkillSimilarity(trigger_threshold=0.3, llm_threshold=0.7, llm_call=mock_llm)
        consolidator = SkillConsolidator(llm_call=mock_llm)
        usage = UsageTracker(tmp_dir / ".usage.json")
        mgr = SkillManager(loader, sim, consolidator, usage)

        asyncio.run(
            mgr.create("deploy-docker", "Docker 部署", ["deploy", "docker"], [], "Docker 部署流程")
        )
        result = asyncio.run(
            mgr.create("deploy-k8s", "K8s 部署", ["deploy", "k8s"], [], "K8s 部署流程")
        )
        assert result["success"]
        assert result["action"] == "merged"
        assert result["name"] == "merged-deploy"


class TestUsageTracker:
    def test_on_create(self, tmp_dir):
        tracker = UsageTracker(tmp_dir / ".usage.json")
        tracker.on_create("my-skill", source="manual")
        stats = tracker.get_stats("my-skill")
        assert stats is not None
        assert stats["source"] == "manual"
        assert stats["created_at"] is not None

    def test_on_view_and_use(self, tmp_dir):
        tracker = UsageTracker(tmp_dir / ".usage.json")
        tracker.on_view("skill-a")
        tracker.on_view("skill-a")
        tracker.on_use("skill-a")
        stats = tracker.get_stats("skill-a")
        assert stats["views"] == 2
        assert stats["uses"] == 1

    def test_on_delete(self, tmp_dir):
        tracker = UsageTracker(tmp_dir / ".usage.json")
        tracker.on_create("temp-skill")
        tracker.on_delete("temp-skill")
        assert tracker.get_stats("temp-skill") is None

    def test_on_merge(self, tmp_dir):
        tracker = UsageTracker(tmp_dir / ".usage.json")
        tracker.on_create("old-a")
        tracker.on_use("old-a")
        tracker.on_use("old-a")
        tracker.on_create("old-b")
        tracker.on_use("old-b")

        tracker.on_merge("merged", ["old-a", "old-b"])
        assert tracker.get_stats("old-a") is None
        assert tracker.get_stats("old-b") is None
        merged = tracker.get_stats("merged")
        assert merged["uses"] == 3  # 2 + 1
        assert merged["source"] == "merged"

    def test_persistence(self, tmp_dir):
        path = tmp_dir / ".usage.json"
        t1 = UsageTracker(path)
        t1.on_create("persist-test")
        t1.on_use("persist-test")

        t2 = UsageTracker(path)
        stats = t2.get_stats("persist-test")
        assert stats is not None
        assert stats["uses"] == 1

    def test_get_all_stats(self, tmp_dir):
        tracker = UsageTracker(tmp_dir / ".usage.json")
        tracker.on_create("skill-x")
        tracker.on_create("skill-y")
        all_stats = tracker.get_all_stats()
        assert "skill-x" in all_stats
        assert "skill-y" in all_stats
