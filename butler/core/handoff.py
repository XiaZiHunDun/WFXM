"""Structured handoff blocks for delegate_task and workflows (agency NEXUS subset)."""

from __future__ import annotations

from typing import Any

_HANDOFF_MARKER = "## Handoff"


def render_handoff_block(
    *,
    from_role: str = "",
    to_role: str = "",
    task: str = "",
    current_state: str = "",
    deliverable: str = "",
    acceptance: list[str] | None = None,
    evidence_required: list[str] | None = None,
    relevant_files: list[str] | None = None,
    prior_report: Any = None,
) -> str:
    """Build markdown handoff section for delegate context."""
    lines = [_HANDOFF_MARKER]
    if from_role or to_role:
        lines.append(f"- 交接: {from_role or '?'} → {to_role or '?'}")
    if task.strip():
        lines.append(f"- 目标: {task.strip()[:300]}")
    if current_state.strip():
        lines.append(f"- 已完成: {current_state.strip()[:400]}")
    if deliverable.strip():
        lines.append(f"- 交付物: {deliverable.strip()[:300]}")
    acc = [str(a).strip() for a in (acceptance or []) if str(a).strip()]
    if acc:
        lines.append("- 验收标准:")
        lines.extend(f"  - {a}" for a in acc[:8])
    ev = [str(e).strip() for e in (evidence_required or []) if str(e).strip()]
    if ev:
        lines.append("- 证据要求:")
        lines.extend(f"  - {e}" for e in ev[:6])
    paths = [str(p).strip() for p in (relevant_files or []) if str(p).strip()]
    if paths:
        lines.append("- 相关路径:")
        lines.extend(f"  - `{p}`" for p in paths[:12])
    if prior_report is not None:
        summary = _report_summary(prior_report)
        if summary:
            lines.append(f"- 上一步摘要: {summary[:400]}")
    return "\n".join(lines)


def _report_summary(report: Any) -> str:
    if report is None:
        return ""
    if hasattr(report, "headline"):
        parts = [str(getattr(report, "headline", "") or "")]
        if getattr(report, "issues", None):
            parts.append(f"issues={len(report.issues)}")
        return " ".join(p for p in parts if p).strip()
    if isinstance(report, dict):
        return str(report.get("headline") or report.get("summary") or "")[:400]
    return str(report)[:400]


def merge_handoff_into_context(
    context: str,
    handoff: str,
    *,
    force: bool = False,
) -> str:
    """Append handoff block unless context already contains one."""
    ctx = str(context or "").strip()
    if not force and _HANDOFF_MARKER in ctx:
        return ctx
    if not handoff.strip():
        return ctx
    if ctx:
        return f"{ctx}\n\n{handoff.strip()}"
    return handoff.strip()


def handoff_from_report(
    report: Any,
    *,
    to_role: str,
    from_role: str = "",
    acceptance: list[str] | None = None,
) -> str:
    """Build handoff from AgentReport after a workflow/delegate step."""
    files: list[str] = []
    issues: list[str] = []
    if hasattr(report, "changes"):
        for ch in report.changes or []:
            f = str(getattr(ch, "file", "") or "").strip()
            if f:
                files.append(f)
    elif isinstance(report, dict):
        for ch in report.get("changes") or []:
            if isinstance(ch, dict) and ch.get("file"):
                files.append(str(ch["file"]))
        issues = list(report.get("issues") or [])
    default_acc = acceptance or [
        "产出符合任务描述",
        "关键路径已 read_file 或测试验证",
    ]
    if issues:
        default_acc.append(f"需处理 {len(issues)} 个已报告问题")
    return render_handoff_block(
        from_role=from_role,
        to_role=to_role,
        deliverable=str(getattr(report, "headline", "") or "")[:200],
        acceptance=default_acc,
        evidence_required=["pytest 或等价验证", "read_file 核对改动"],
        relevant_files=files,
        prior_report=report,
    )


__all__ = [
    "handoff_from_report",
    "merge_handoff_into_context",
    "render_handoff_block",
]
