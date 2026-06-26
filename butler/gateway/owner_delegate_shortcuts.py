"""Owner shortcuts: /改 → dev delegate NL, /转交CC → CC handoff package (PROD-P4-B)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_edit_command_arg(arg: str) -> tuple[str, str]:
    """Split ``/改 <path> <goal>`` — first token path, remainder goal."""
    body = str(arg or "").strip()
    if not body:
        return "", ""
    parts = body.split(maxsplit=1)
    path = parts[0].strip()
    goal = parts[1].strip() if len(parts) > 1 else "按说明修改"
    return path, goal


def build_dev_delegate_prompt(
    path: str,
    goal: str,
    *,
    project_name: str = "",
) -> str:
    """Standardized dev delegate phrase for Lead (role=dev, scoped)."""
    path = str(path or "").strip() or "docs/"
    goal = str(goal or "").strip() or "按说明修改"
    proj = f"当前项目 {project_name}。" if project_name else ""
    return (
        f"请委派开发代理（role=dev，禁止 run_workflow）。{proj}"
        f"限定范围：{path}。目标：{goal}。"
        "改完后 read_file 确认；不要改范围外文件；不要开 terminal 除非 VERIFY 需要。"
    )


def try_expand_owner_edit_slash(text: str, *, project_name: str = "") -> str | None:
    """
    Expand ``/改 <path> <goal>`` to delegate NL before the agent loop.

    Returns ``None`` if not ``/改`` or missing args (slash handler shows usage).
    """
    raw = str(text or "").strip()
    if not raw.lower().startswith("/改"):
        return None
    arg = raw.split(maxsplit=1)[1].strip() if len(raw.split(maxsplit=1)) > 1 else ""
    if not arg:
        return None
    path, goal = parse_edit_command_arg(arg)
    if not path:
        return None
    return build_dev_delegate_prompt(path, goal, project_name=project_name)


def format_edit_command_usage() -> str:
    return (
        "用法：/改 <路径或范围> <目标>\n"
        "例：/改 docs/foo.md 加一段说明\n"
        "例：/改 src/auth.py 修复登录校验\n"
        "将自动交给开发代理（限定文件范围）。"
    )


def _recent_read_paths(session_key: str, *, limit: int = 5) -> list[str]:
    try:
        from butler.core.session_tool_index import list_session_read_files

        return list_session_read_files(session_key, limit=limit)
    except Exception:
        return []


def build_cc_handoff_package(
    scope: str,
    *,
    project_name: str = "",
    workspace: str | Path = "",
    session_key: str = "",
) -> str:
    """Markdown task pack for local Claude Code / Cursor (P4-04)."""
    scope = str(scope or "").strip() or "（请补充范围）"
    proj = str(project_name or "").strip() or "（未选项目）"
    ws = str(workspace or "").strip() or "—"
    reads = _recent_read_paths(session_key)

    lines = [
        "【CC 任务包】复制到本机 Claude Code / Cursor",
        "",
        "## 范围",
        scope,
        "",
        "## 项目",
        proj,
        "",
        "## 工作区",
        ws,
    ]
    if reads:
        lines.extend(["", "## 相关文件（本会话已读）", *[f"- `{p}`" for p in reads[:5]]])

    lines.extend(
        [
            "",
            "## 现状",
            "- 微信 Butler 负责派工与验收摘要；大改码/全库 refactor 建议本机 CC 执行",
            "- 完成后可将 PR 链接或变更摘要发回微信",
            "",
            "## Butler 侧下一步",
        ]
    )

    try:
        from butler.runtime.cc_bridge import cc_bridge_enabled

        cc_on = cc_bridge_enabled()
    except Exception:
        cc_on = False

    if cc_on:
        brief = scope.replace("\n", " ")[:160]
        lines.append(f"- 网关已开 CC 桥接：发 **/cc-bridge {brief}**")
    else:
        lines.append("- 本机执行；或设 `BUTLER_CC_BRIDGE=1` 后用 **/cc-bridge <摘要>**")

    lines.append("- 验收：改完后在微信发「交给开发代理：只读检查 …」或看委派 **验收卡**")
    return "\n".join(lines)


def resolve_project_context(orchestrator: Any, session_key: str) -> tuple[str, str]:
    """Return (display_name, workspace_path) for current project."""
    pm = getattr(orchestrator, "project_manager", None)
    if pm is None:
        return "", ""
    proj = pm.get_current(session_key=str(session_key or "").strip())
    if proj is None:
        return "", ""
    name = str(getattr(proj, "name", "") or "").strip()
    ws = str(getattr(proj, "workspace", "") or "").strip()
    return name, ws


__all__ = [
    "build_cc_handoff_package",
    "build_dev_delegate_prompt",
    "format_edit_command_usage",
    "parse_edit_command_arg",
    "resolve_project_context",
    "try_expand_owner_edit_slash",
]
