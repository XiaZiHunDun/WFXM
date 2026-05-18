"""Memory tools — layered memory management (butler + project).

Uses ButlerMemory for owner preferences/experience and ProjectMemory for
project-specific technical knowledge.
"""

from __future__ import annotations

from butler.tools.registry import register_tool


@register_tool(
    name="remember",
    description="记住一条重要信息。butler 范围存入管家层（偏好/经验），project 范围存入项目层（技术细节）。",
    parameters={
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "description": "记忆分类",
                "enum": ["架构与设计", "关键决策", "代码模式与约定", "已知问题", "当前状态", "主公偏好", "经验教训"],
            },
            "content": {"type": "string", "description": "要记住的内容"},
            "scope": {
                "type": "string",
                "description": "记忆范围: project=当前项目, butler=管家层偏好, experience=跨项目经验",
                "enum": ["project", "butler", "experience"],
            },
        },
        "required": ["section", "content"],
    },
    category="memory",
)
def remember(section: str, content: str, scope: str = "project") -> dict:
    if scope == "butler":
        butler_mem = _get_butler_memory()
        result = butler_mem.add_profile(content)
        if result.get("success"):
            return {"success": True, "scope": "butler", "message": f"已记住管家层偏好: {content[:50]}..."}
        return result
    elif scope == "experience":
        butler_mem = _get_butler_memory()
        from butler.core.project_manager import project_manager
        butler_mem.add_experience(content, category=section, project=project_manager.current_project or "")
        return {"success": True, "scope": "experience", "message": f"已记住跨项目经验: {content[:50]}..."}
    else:
        proj_mem = _get_project_memory()
        if proj_mem is None:
            return {"error": "无当前项目，无法存储项目记忆"}
        classification = proj_mem.append_with_classification(section, content)
        msg = f"已记住 [{section}] {content[:50]}..."
        if classification == "decision":
            msg += " (已标记为待审核决策)"
        return {"success": True, "scope": "project", "classification": classification, "message": msg}


@register_tool(
    name="recall",
    description="回忆记忆内容。可以回忆管家层记忆、当前项目记忆或两者。",
    parameters={
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "description": "记忆范围: project=项目, butler=管家, both=两者",
                "enum": ["project", "butler", "both"],
            },
            "topic": {"type": "string", "description": "要回忆的主题（留空则返回摘要）"},
        },
        "required": [],
    },
    category="memory",
)
def recall(scope: str = "both", topic: str = "") -> dict:
    result = {}

    if scope in ("project", "both"):
        proj_mem = _get_project_memory()
        if proj_mem:
            if topic:
                context = proj_mem.get_context_for_agent("dev_agent", task=topic)
                result["project_memory"] = context
            else:
                result["project_memory"] = proj_mem.get_full_context(max_lines=40)

    if scope in ("butler", "both"):
        butler_mem = _get_butler_memory()
        if topic:
            experiences = butler_mem.search_experience(topic, limit=5)
            result["butler_profile"] = butler_mem.profile.format_for_prompt()
            if experiences:
                result["butler_experience"] = experiences
        else:
            result["butler_memory"] = butler_mem.get_system_context()

    return result if result else {"message": "暂无记忆"}


@register_tool(
    name="approve_memory",
    description="审核待批准的决策记忆（将待审核的决策正式写入项目记忆）",
    parameters={
        "type": "object",
        "properties": {
            "indices": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "要批准的条目索引列表（留空则批准全部）",
            },
        },
        "required": [],
    },
    category="memory",
)
def approve_memory(indices: list[int] | None = None) -> dict:
    proj_mem = _get_project_memory()
    if proj_mem is None:
        return {"error": "无当前项目"}
    pending = proj_mem.get_pending_decisions()
    if not pending:
        return {"message": "无待审核的决策记忆"}
    approved = proj_mem.approve_pending(indices)
    return {"success": True, "approved_count": approved, "remaining": len(pending) - approved}


def _get_butler_memory():
    from butler.storage.butler_memory import ButlerMemory
    return ButlerMemory.default()


def _get_project_memory():
    from butler.storage.project_memory import ProjectMemory
    from butler.core.project_manager import project_manager
    if project_manager.current_project:
        return ProjectMemory.for_project_name(project_manager.current_project)
    return None
