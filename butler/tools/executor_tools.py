"""Executor delegation tools - Butler spawns SubAgents via these tools.

v3: Returns structured AgentReport instead of truncated response text.
The report is also cached on Butler for progressive disclosure (/detail).
"""

from __future__ import annotations

from butler.tools.registry import register_tool


@register_tool(
    name="delegate_to_dev_agent",
    description="将代码开发任务委派给 DevAgent 执行（修 bug、写功能、重构、测试等）。DevAgent 可以读写文件、执行命令、搜索代码、Git 操作，使用项目配置的开发模型。",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "要执行的开发任务描述"},
            "project": {"type": "string", "description": "项目名称（留空则用当前项目）"},
            "context": {"type": "string", "description": "额外上下文信息（可选）"},
            "max_turns": {"type": "integer", "description": "最大轮次，默认 30"},
        },
        "required": ["task"],
    },
    is_async=True,
    category="executor",
)
async def delegate_to_dev_agent(
    task: str,
    project: str = "",
    context: str = "",
    max_turns: int = 30,
) -> dict:
    return await _delegate("dev_agent", task, project, context, max_turns)


@register_tool(
    name="delegate_to_content_agent",
    description="将内容创作任务委派给 ContentAgent（小说、文档、文案等），使用项目配置的内容模型。",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "创作任务描述"},
            "project": {"type": "string", "description": "项目名称（留空则用当前项目）"},
            "context": {"type": "string", "description": "额外上下文（如参考文件内容）"},
            "output_file": {"type": "string", "description": "将结果保存到的文件路径（可选）"},
        },
        "required": ["task"],
    },
    is_async=True,
    category="executor",
)
async def delegate_to_content_agent(
    task: str,
    project: str = "",
    context: str = "",
    output_file: str = "",
) -> dict:
    full_task = task
    if output_file:
        full_task += f"\n\n请将最终结果写入文件: {output_file}"
    return await _delegate("content_agent", full_task, project, context, max_turns=15)


@register_tool(
    name="delegate_to_review_agent",
    description="将审核任务委派给 ReviewAgent（代码审查、内容审核、质量检查）",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "审核任务描述"},
            "project": {"type": "string", "description": "项目名称（留空则用当前项目）"},
            "context": {"type": "string", "description": "额外上下文"},
        },
        "required": ["task"],
    },
    is_async=True,
    category="executor",
)
async def delegate_to_review_agent(
    task: str,
    project: str = "",
    context: str = "",
) -> dict:
    return await _delegate("review_agent", task, project, context, max_turns=10)


async def _delegate(
    role: str,
    task: str,
    project: str,
    context: str,
    max_turns: int,
) -> dict:
    """Shared delegation logic for all agent types."""
    from butler.core.project_manager import project_manager
    from butler.core.report_formatter import format_for_butler_tool_result
    from butler.executors.agent_runner import AgentRunner
    from butler.executors.agent_profiles import get_profile, get_model_aware_prompt_extra

    project = project or project_manager.current_project
    if not project:
        return {"error": "未指定项目，也没有当前活跃项目"}
    proj = project_manager.get_project(project)
    if not proj:
        return {"error": f"项目 '{project}' 不存在"}

    profile = get_profile(role)
    if not profile:
        return {"error": f"未知角色: {role}"}
    model_config = proj.resolve_model(role)

    if model_config.is_empty():
        return {"error": f"未配置可用的模型。请通过 /model {role.split('_')[0]} <provider>:<model> 设置。"}

    project_context = _build_project_context(proj, role=role)

    skill_context = _match_skills_for_task(proj, task)
    if skill_context:
        project_context += f"\n\n{skill_context}"

    if context:
        project_context += f"\n\n额外上下文:\n{context}"

    system_prompt = profile.system_prompt + get_model_aware_prompt_extra(model_config.provider)

    runner = AgentRunner(
        model_config=model_config,
        tools=profile.tools,
        system_prompt=system_prompt,
        max_turns=max_turns,
    )

    progress_callback = _get_progress_callback()
    result = await runner.run(task=task, context=project_context, on_turn=progress_callback)

    # Cache the full report on Butler for /detail access
    _cache_report_on_butler(result)

    tool_result = format_for_butler_tool_result(result.report, result.milestones)
    tool_result.update({
        "success": result.success,
        "project": project,
        "model": f"{model_config.provider}:{model_config.model}",
        "turns_used": result.turns_used,
        "error": result.error,
    })
    return tool_result


def _get_progress_callback():
    """Return a progress callback if there's an active progress handler."""
    from butler.core import _progress_handler
    handler = _progress_handler.get()
    if handler is None:
        return None

    def on_turn(turn: int, tool_name: str, brief: str):
        handler(turn, tool_name, brief)

    return on_turn


def _cache_report_on_butler(result) -> None:
    """Cache the latest agent result on the active Butler instance."""
    from butler.core import _last_report_cache
    _last_report_cache.set(result)


@register_tool(
    name="run_workflow",
    description="执行项目工作流操作（查看状态、初始化、推进步骤、重置）",
    parameters={
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "项目名称（留空则用当前项目）"},
            "workflow": {"type": "string", "description": "工作流名称"},
            "command": {
                "type": "string", "description": "命令",
                "enum": ["status", "init", "advance", "reset"],
            },
        },
        "required": ["workflow", "command"],
    },
    is_async=True,
    category="executor",
)
async def run_workflow(workflow: str, command: str = "status", project: str = "") -> str:
    from butler.core.project_manager import project_manager
    from butler.executors.workflow_engine import WorkflowEngine

    project = project or project_manager.current_project
    if not project:
        return '{"error": "未指定项目"}'

    engine = WorkflowEngine()
    return await engine.execute(project_name=project, task=f"{workflow}:{command}")


def _build_project_context(proj, role: str = "dev_agent") -> str:
    """Build context string from project memory, scoped by agent role."""
    from butler.storage.project_memory import ProjectMemory

    parts: list[str] = [f"项目: {proj.name} ({proj.type})", f"描述: {proj.description}"]

    try:
        proj_mem = ProjectMemory.for_project(proj)
        mem_context = proj_mem.get_context_for_agent(role)
        if mem_context and mem_context != "(暂无项目记忆)":
            parts.append(f"\n{mem_context}")
    except Exception:
        memory_file = proj.workspace / ".butler" / "memory" / "MEMORY.md"
        if memory_file.exists():
            try:
                content = memory_file.read_text(encoding="utf-8")[:3000]
                parts.append(f"\n项目记忆:\n{content}")
            except Exception:
                pass

    return "\n".join(parts)


def _match_skills_for_task(proj, task: str) -> str:
    """Match relevant skills for the task via SkillRouter and return context."""
    try:
        from butler.config.settings import settings
        from butler.skills.loader import SkillLoader
        from butler.skills.router import SkillRouter

        global_dir = settings.butler_home / "skills"
        project_dir = proj.workspace / ".butler" / "skills"
        loader = SkillLoader(
            project_skills_dir=project_dir if project_dir.exists() else None,
            global_skills_dir=global_dir if global_dir.exists() else None,
        )
        all_skills = loader.list_skills(scope="all")
        if not all_skills:
            return ""

        router = SkillRouter()
        matched = router.match(task, all_skills, top_k=2)
        if not matched:
            return ""

        parts = ["## 匹配的 Skill 工作流（请参考执行）"]
        for skill in matched:
            parts.append(f"\n### Skill: {skill.name}")
            parts.append(f"> {skill.description}")
            body = skill.body[:3000] if len(skill.body) > 3000 else skill.body
            parts.append(body)

        return "\n".join(parts)
    except Exception:
        return ""
