"""Owner-facing surfaces: tier-1 help, status health, project switch brief."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_OWNER_HELP_DEFAULT = """Butler — 五个说法就够

查  /状态  /简报  — 什么状况、今天要干嘛
改  /改 <路径> <目标> 或 交给开发代理…  — 小改动与测试
批  /确认  /停止  — 流程与中断
记  刚才不对…  /反馈  — 纠正我
管  /切换  /项目  /分工  — 项目与和 CC 配合

详细命令：/帮助 高级"""


def format_owner_help_default() -> str:
    return _OWNER_HELP_DEFAULT.strip()


def format_owner_help_advanced() -> str:
    from butler.gateway.commands.help_handlers import _HELP_GROUPS

    lines = [
        "Butler 全部命令（/帮助 <主题> 可看单组）",
        "",
        "主题：项目 · 对话 · 记忆 · 权限 · 开发 · 日常 · 管理 · 规划 · 模型",
        "",
    ]
    for group, (title, _body) in _HELP_GROUPS.items():
        lines.append(f"  /帮助 {group} — {title}")
    lines.append("")
    lines.append("运维：/诊断 详细（全量）· /doctor（安全审计）")
    return "\n".join(lines)


def _health_icon(ok: bool, warn: bool = False) -> str:
    if ok:
        return "🟢"
    if warn:
        return "🟡"
    return "🔴"


def format_owner_status_header(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict | None = None,
) -> list[str]:
    """Owner-readable health lines for /状态 (non-technical)."""
    from butler.ops.butler_inbox import collect_inbox_snapshot, _action_count

    sk = str(session_key or "").strip()
    snap = collect_inbox_snapshot(orchestrator, sk, health=health)
    actions = _action_count(snap)

    proj_ok = bool(snap.project_name and snap.project_name != "(无)")
    model_ok = bool(getattr(orchestrator, "_settings", None) and orchestrator._settings.default_provider)

    pending_delegate = _pending_delegate_line(sk)
    delegate_warn = bool(pending_delegate)

    lines = [
        "健康概览",
        f"  {_health_icon(True)} 网关在线",
        f"  {_health_icon(proj_ok)} 当前项目：{snap.project_name or '未选择'}",
        f"  {_health_icon(model_ok)} 模型通道：{orchestrator._settings.default_provider if model_ok else '未配置'}",
        f"  {_health_icon(actions == 0, warn=actions > 0)} 待处理："
        + (f"{actions} 类 → /简报" if actions else "无"),
    ]
    if pending_delegate:
        lines.append(f"  {_health_icon(False, warn=True)} {pending_delegate}")

    prof = os.getenv("BUTLER_ENV_PROFILE", "").strip()
    if prof:
        lines.append(f"  环境：{prof}（lead=生产关 terminal · dev-gateway=Linux 沙箱）")

    return lines


def _pending_delegate_line(session_key: str) -> str:
    from butler.gateway.owner_surface_ops import pending_delegate_line_safe

    return pending_delegate_line_safe(session_key)


def format_project_switch_brief(
    orchestrator: Any,
    session_key: str,
    project_name: str,
) -> str:
    """Three-line (+ lead hint) summary after /切换."""
    from butler.project.lead import is_lead_project
    from butler.project.meta import lifecycle_label

    pm = orchestrator.project_manager
    proj = pm.get_project(project_name) or pm.get_current(session_key=session_key)
    lines = ["", "── 项目摘要 ──"]

    lc = lifecycle_label(proj) if proj else "active"
    pack = (getattr(proj, "pack", "") or "").strip() if proj else ""
    state_bits = [f"状态 {lc or 'active'}"]
    if pack:
        state_bits.append(f"能力包 {pack}")
    lines.append(f"· {' · '.join(state_bits)}")

    ws = Path(getattr(proj, "workspace", "") or "") if proj else None
    if ws and ws.is_dir():
        from butler.gateway.owner_surface_ops import project_todos_brief_safe

        brief = project_todos_brief_safe(ws)
        if brief:
            lines.append(brief)

    delegate_line = _pending_delegate_line(session_key)
    if delegate_line:
        lines.append(f"· {delegate_line}")
    else:
        lines.append("· 委派：无进行中的后台任务")

    if proj and is_lead_project(proj.name, project=proj):
        lines.append(
            "· 建议：改代码说「交给开发代理…」；只读巡检用 /运行；Lead 不直接开 terminal"
        )

    return "\n".join(lines)


def _owner_outbound_brief_line(*, session_key: str = "", chat_id: str = "") -> str | None:
    from butler.gateway.owner_surface_ops import outbound_brief_line_safe

    return outbound_brief_line_safe(session_key=session_key, chat_id=chat_id)


def _owner_degradation_brief_line(
    orchestrator: Any,
    *,
    session_key: str = "",
    health: dict | None = None,
) -> str | None:
    from butler.gateway.owner_surface_ops import degradation_brief_line_safe

    return degradation_brief_line_safe(
        orchestrator,
        session_key=session_key,
        health=health,
    )


def _owner_memory_degradation_brief_line(
    orchestrator: Any,
    *,
    session_key: str = "",
    health: dict | None = None,
) -> str | None:
    """Backward-compat alias — prefer :func:`_owner_degradation_brief_line`."""
    return _owner_degradation_brief_line(
        orchestrator, session_key=session_key, health=health
    )


def format_owner_diagnostic_brief(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict | None = None,
) -> str:
    """Owner-tier /诊断 — three human lines; full ops via ``/诊断 详细``."""
    from butler.ops.butler_inbox import collect_inbox_snapshot, _action_count

    sk = str(session_key or "").strip()
    snap = collect_inbox_snapshot(orchestrator, sk, health=health)
    actions = _action_count(snap)

    proj_ok = bool(snap.project_name and snap.project_name != "(无)")
    proj_name = snap.project_name or "未选择"

    delegate = _pending_delegate_line(sk)
    todo_warn = actions > 0 or bool(delegate)

    lines = [
        "Butler 简要诊断",
        "",
        f"网关：{_health_icon(True)} 在线",
        f"项目：{_health_icon(proj_ok)} {proj_name}",
    ]
    if todo_warn:
        bits: list[str] = []
        if actions:
            bits.append(f"{actions} 类待关注")
        if delegate:
            bits.append("委派进行中")
        lines.append(f"待办：{_health_icon(False, warn=True)} {' · '.join(bits)} → /简报")
    else:
        lines.append(f"待办：{_health_icon(True)} 无")

    outbound = _owner_outbound_brief_line(session_key=sk)
    if outbound:
        lines.append(outbound)

    degradation = _owner_degradation_brief_line(
        orchestrator, session_key=sk, health=health
    )
    if degradation:
        lines.append(degradation)

    lines.append("")
    lines.append("完整快照：/诊断 详细")
    return "\n".join(lines)


_CC_COMPLEMENT_TEXT = """Butler 与 Claude Code / Cursor 分工

· 微信 Butler（莎丽）：远程统筹、多项目记忆、委派派工、门控与验收
· Butler 委派 dev：常规改码、pytest、项目内配置（project.yaml 等）
· CC CLI（/cc-bridge）：网关宿主机上的 claude 命令，适合重 refactor
· 本机 Cursor/CC：人在电脑前时的 IDE + LSP

推荐路径：
  查状态 / 读文件 → 直接说
  改代码 / 跑测试 → 「交给开发代理…」或 /运行
  重编码 / 长环修复 → /cc-bridge …（需 BUTLER_CC_BRIDGE=1）
  沙箱 / npm 被挡 → /沙箱 · /批准沙箱外

相关：/今日 · /简报 · /帮助 开发"""


def format_cc_complement_message() -> str:
    return _CC_COMPLEMENT_TEXT.strip()


def format_project_today_view(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict | None = None,
) -> str:
    """Owner one-screen: health + todos + delegate + reminders + next actions."""
    from butler.ops.butler_inbox import collect_inbox_snapshot

    sk = str(session_key or "").strip()
    snap = collect_inbox_snapshot(orchestrator, sk, health=health)
    lines = ["📅 今日 · " + (snap.project_name or "未选项目"), ""]
    lines.extend(format_owner_status_header(orchestrator, sk, health=health))
    lines.append("")

    lines.append("优先事项")
    any_item = False
    if snap.project_todos_open:
        any_item = True
        lines.append(f"· 待办 {snap.project_todos_open} 项")
        for item in snap.project_todo_samples[:2]:
            lines.append(f"  - {item}")
        if snap.project_todos_open > 2:
            lines.append("  … → /项目待办")
    delegate = _pending_delegate_line(sk)
    if delegate:
        any_item = True
        lines.append(f"· {delegate}")
    if snap.reminders_pending:
        any_item = True
        lines.append(f"· 提醒 {snap.reminders_pending} 个待触发")
        for item in snap.reminder_samples[:2]:
            lines.append(f"  - {item}")
    if snap.memory_pending:
        any_item = True
        lines.append(f"· 记忆待审 {snap.memory_pending} 条 → /记忆待审")
    if snap.workflow_gate:
        any_item = True
        lines.append(f"· {snap.workflow_gate[:100]}")
    if not any_item:
        lines.append("· 暂无紧急项 ✅")

    lines.append("")
    lines.append("快捷入口：/运行 · /工作流 · /委派质量 · /分工")
    return "\n".join(lines)


def _runtime_jobs_owner_lines(workspace: Path) -> list[str]:
    from butler.gateway.owner_surface_ops import runtime_jobs_lines_safe

    return runtime_jobs_lines_safe(workspace)


def format_project_overview_owner(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict | None = None,
) -> str:
    """Owner-friendly /项目概况 — action-oriented, not file/git stats."""
    from butler.ops.butler_inbox import collect_inbox_snapshot
    from butler.project.lead import is_lead_project
    from butler.project.meta import lifecycle_label

    pm = orchestrator.project_manager
    proj = pm.get_current(session_key=str(session_key or "").strip())
    if proj is None:
        return "请先 /切换 到目标项目"

    ws = Path(getattr(proj, "workspace", "") or "")
    if not ws.is_dir():
        return f"项目 {proj.name} 的工作区不可用"

    snap = collect_inbox_snapshot(orchestrator, session_key, health=health)
    lc = lifecycle_label(proj)
    pack = (getattr(proj, "pack", "") or "").strip()
    lines = [f"📊 {proj.name} · 项目概况", ""]

    meta = [f"状态 {lc or 'active'}"]
    if pack:
        meta.append(f"能力 {pack}")
    if is_lead_project(proj.name, project=proj):
        meta.append("Lead")
    lines.append("· " + " · ".join(meta))

    lines.append("")
    lines.append("今日焦点")
    if snap.project_todos_open:
        lines.append(f"· 待办 {snap.project_todos_open} 项")
        for item in snap.project_todo_samples[:3]:
            lines.append(f"  - {item}")
    else:
        lines.append("· 待办：无未完成项")

    delegate = _pending_delegate_line(session_key)
    if delegate:
        lines.append(f"· {delegate}")

    if snap.reminders_pending:
        lines.append(f"· 提醒 {snap.reminders_pending} 个待触发")

    if snap.memory_pending:
        lines.append(f"· 记忆待审 {snap.memory_pending} 条 → /记忆待审")

    if snap.workflow_gate:
        lines.append(f"· {snap.workflow_gate[:90]}")

    lines.extend(_runtime_jobs_owner_lines(ws))

    dev = dict(getattr(proj, "dev", None) or {})
    if dev.get("test_command"):
        lines.append("· 验收：委派 dev 后会跑 project.yaml 测试命令")

    if is_lead_project(proj.name, project=proj):
        lines.append("· 建议：改代码走委派；重编码用本机 CC → /分工")

    lines.append("")
    lines.append("更多：/今日 · /简报 · /项目待办")
    lines.append("运维统计：/项目概况 详细")
    return "\n".join(lines)


__all__ = [
    "format_cc_complement_message",
    "format_owner_diagnostic_brief",
    "format_owner_help_advanced",
    "format_owner_help_default",
    "format_owner_status_header",
    "format_project_overview_owner",
    "format_project_switch_brief",
    "format_project_today_view",
]
