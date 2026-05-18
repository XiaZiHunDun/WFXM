"""Skill tools — Agent-accessible skill management.

skill_create goes through SkillManager which triggers the three-layer
similarity funnel + LLM merge when a similar skill is detected.
"""
from __future__ import annotations

import logging

from butler.config.settings import settings
from butler.core.project_manager import project_manager
from butler.skills.loader import SkillLoader
from butler.tools.registry import register_tool

logger = logging.getLogger(__name__)

_loader = None
_manager = None


def _get_loader() -> SkillLoader:
    global _loader
    if _loader is None:
        global_dir = settings.butler_home / "skills"
        project_dir = None
        proj = project_manager.get_current()
        if proj:
            project_dir = proj.workspace / ".butler" / "skills"
        _loader = SkillLoader(project_skills_dir=project_dir, global_skills_dir=global_dir)
    return _loader


def _get_manager():
    """Lazy-init SkillManager with similarity/consolidator wired to LLM."""
    global _manager
    if _manager is not None:
        return _manager

    from butler.skills.consolidator import SkillConsolidator
    from butler.skills.manager import SkillManager
    from butler.skills.similarity import SkillSimilarity
    from butler.skills.usage import UsageTracker

    loader = _get_loader()
    global_dir = settings.butler_home / "skills"
    usage = UsageTracker(global_dir / ".usage.json")

    similarity = SkillSimilarity(
        trigger_threshold=0.3,
        tfidf_threshold=0.5,
        llm_threshold=0.7,
    )
    consolidator = SkillConsolidator()

    _manager = SkillManager(
        skill_loader=loader,
        similarity=similarity,
        consolidator=consolidator,
        usage_tracker=usage,
    )
    return _manager


def reset_loader() -> None:
    """Reset cached loader (call on project switch)."""
    global _loader, _manager
    _loader = None
    _manager = None


@register_tool(
    name="skill_list",
    description="列出可用的 Skill（可复用工作流程）。scope 可选: all/project/global",
    parameters={
        "type": "object",
        "properties": {
            "scope": {"type": "string", "description": "范围: all, project, global", "enum": ["all", "project", "global"]},
        },
        "required": [],
    },
    category="knowledge",
    read_only=True,
)
def skill_list(scope: str = "all") -> dict:
    loader = _get_loader()
    skills = loader.list_skills(scope=scope)
    return {
        "skills": [
            {"name": s.name, "description": s.description, "scope": s.scope,
             "triggers": s.triggers[:3]}
            for s in skills
        ],
        "count": len(skills),
    }


@register_tool(
    name="skill_view",
    description="查看 Skill 的完整内容（工作流程步骤）",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill 名称"},
        },
        "required": ["name"],
    },
    category="knowledge",
    read_only=True,
)
def skill_view(name: str) -> dict:
    loader = _get_loader()
    skill = loader.get_skill(name)
    if not skill:
        return {"error": f"Skill '{name}' 不存在。使用 skill_list 查看可用 skill。"}
    return {
        "name": skill.name,
        "description": skill.description,
        "triggers": skill.triggers,
        "tools": skill.tools,
        "scope": skill.scope,
        "body": skill.body,
    }


@register_tool(
    name="skill_create",
    description=(
        "创建新的 Skill（可复用工作流程）。如果检测到与已有 skill 高度相似，"
        "会自动通过 LLM 合并为一条更完整的 skill。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill 名称 (kebab-case)"},
            "description": {"type": "string", "description": "一句话描述"},
            "triggers": {"type": "array", "items": {"type": "string"}, "description": "触发词列表"},
            "tools": {"type": "array", "items": {"type": "string"}, "description": "使用的工具列表"},
            "body": {"type": "string", "description": "工作流程 Markdown 内容"},
            "scope": {"type": "string", "description": "范围: project 或 global", "enum": ["project", "global"]},
        },
        "required": ["name", "description", "body"],
    },
    is_async=True,
    category="knowledge",
)
async def skill_create(
    name: str, description: str, body: str,
    triggers: list[str] | None = None, tools: list[str] | None = None,
    scope: str = "project",
) -> dict:
    manager = _get_manager()
    return await manager.create(
        name=name,
        description=description,
        triggers=triggers,
        tools=tools,
        body=body,
        scope=scope,
        source="manual",
    )
