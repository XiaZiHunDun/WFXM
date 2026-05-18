"""Project management tools for the Butler."""

from __future__ import annotations

from butler.tools.registry import register_tool


@register_tool(
    name="list_projects",
    description="列出所有已注册的项目及其状态摘要",
    parameters={"type": "object", "properties": {}, "required": []},
    category="project",
)
def list_projects() -> dict:
    from butler.core.project_manager import project_manager
    projects = project_manager.list_projects()
    if not projects:
        return {"message": "当前没有已注册的项目", "projects": []}
    return {
        "current": project_manager.current_project,
        "projects": [
            {
                "name": p.name,
                "type": p.type,
                "status": p.status,
                "description": p.description,
                "is_current": p.name == project_manager.current_project,
            }
            for p in projects
        ],
    }


@register_tool(
    name="switch_project",
    description="切换当前活跃项目",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "要切换到的项目名称"},
        },
        "required": ["name"],
    },
    category="project",
)
def switch_project(name: str) -> dict:
    from butler.core.project_manager import project_manager
    ok = project_manager.switch_project(name)
    if ok:
        proj = project_manager.get_project(name)
        return {"success": True, "message": f"已切换到项目【{name}】", "project": proj.to_dict() if proj else {}}
    return {"success": False, "message": f"项目 '{name}' 不存在"}


@register_tool(
    name="get_project_status",
    description="获取指定项目的详细状态信息",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "项目名称，为空则获取当前项目"},
        },
        "required": [],
    },
    category="project",
)
def get_project_status(name: str = "") -> dict:
    from butler.core.project_manager import project_manager
    name = name or project_manager.current_project
    if not name:
        return {"error": "没有指定项目，也没有当前活跃项目"}
    proj = project_manager.get_project(name)
    if not proj:
        return {"error": f"项目 '{name}' 不存在"}
    return proj.get_full_status()


@register_tool(
    name="create_project",
    description="创建一个新项目",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "项目名称"},
            "type": {
                "type": "string",
                "description": "项目类型",
                "enum": ["software", "content", "research"],
            },
            "description": {"type": "string", "description": "项目描述"},
        },
        "required": ["name", "type", "description"],
    },
    category="project",
)
def create_project(name: str, type: str, description: str) -> dict:
    from butler.core.project_manager import project_manager
    ok = project_manager.create_project(name, type, description)
    if ok:
        return {"success": True, "message": f"项目【{name}】已创建"}
    return {"success": False, "message": f"创建项目 '{name}' 失败（可能已存在）"}
