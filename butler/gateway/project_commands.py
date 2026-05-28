"""WeChat slash commands for project onboarding (/项目 新建|体检)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


def handle_project_onboarding_command(
    orchestrator: "ButlerOrchestrator",
    cmd: str,
    arg: str,
    *,
    session_key: str,
    platform: str = "unknown",
    external_id: str | None = None,
) -> str | None:
    """Handle /项目 新建|体检. Returns None if not matched."""
    if cmd != "/项目":
        return None

    parts = (arg or "").strip().split()
    sub = parts[0].lower() if parts else ""
    rest = parts[1:] if len(parts) > 1 else []

    if sub in ("新建", "create"):
        return _project_create_wechat(
            orchestrator,
            rest,
            platform=platform,
            external_id=external_id,
            session_key=session_key,
        )
    if sub in ("体检", "preflight", "检查"):
        return _project_preflight_wechat(orchestrator, session_key=session_key)

    return None


def _project_create_wechat(
    orchestrator: "ButlerOrchestrator",
    args: list[str],
    *,
    platform: str = "unknown",
    external_id: str | None = None,
    session_key: str = "",
) -> str:
    from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

    if not is_gateway_owner(
        platform=platform,
        external_id=external_id,
        session_key=session_key,
    ):
        return owner_required_message()

    if not args:
        return (
            "用法: /项目 新建 <slug> [模板]\n"
            "  slug: ASCII 目录名，如 MyApp\n"
            "  模板: software-default | novel-factory | knowledge-light\n"
            "显示名默认与 slug 相同；可用 /项目 新建 MyApp 我的应用（第三段起为中文名）"
        )

    slug = args[0]
    template = "software-default"
    display_parts: list[str] = []

    if len(args) >= 2:
        if args[1] in (
            "software-default",
            "novel-factory",
            "knowledge-light",
            "software",
        ):
            template = args[1]
            display_parts = args[2:]
        else:
            display_parts = args[1:]

    display_name = " ".join(display_parts).strip() or slug

    from butler.project.archetypes import validate_slug

    ok, err = validate_slug(slug)
    if not ok:
        return f"新建失败: {err}"

    pm = orchestrator.project_manager
    try:
        created = pm.create_project(
            slug,
            description="",
            display_name=display_name,
            template=template,
            pack="novel-factory" if template == "novel-factory" else "",
        )
    except ValueError as exc:
        return f"新建失败: {exc}"
    except FileNotFoundError as exc:
        return f"新建失败: {exc}"

    if created is None:
        return f"新建失败: 目录或项目名 {display_name!r} 已存在。"

    return (
        f"已创建项目 {created.name!r}\n"
        f"  目录: {created.workspace}\n"
        f"  模板: {template}\n"
        f"下一步:\n"
        f"  1. /切换 {created.name}\n"
        f"  2. /项目 体检\n"
        f"  3. 服务器执行: butler memory-reindex --project {created.name!r}"
    )


def _project_preflight_wechat(
    orchestrator: "ButlerOrchestrator",
    *,
    session_key: str,
) -> str:

    from butler.config import get_butler_settings
    from butler.project.preflight import format_report, run_preflight

    pm = orchestrator.project_manager
    name = pm.resolve_active_project_name(session_key=session_key)
    proj = pm.get_current(session_key=session_key)
    if not name or proj is None:
        return "请先 /切换 到要体检的项目。"

    from butler.project.preflight import resolve_tool_safe_root

    settings = get_butler_settings()
    safe_root = resolve_tool_safe_root()

    report = run_preflight(
        proj.workspace,
        projects_dir=settings.projects_dir,
        safe_root=safe_root,
    )
    text = format_report(report)
    if len(text) > 3500:
        text = text[:3500] + "\n…(已截断，完整结果请用 CLI: butler project preflight)"
    return text
