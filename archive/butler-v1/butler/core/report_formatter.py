"""Channel-adaptive report formatting for AgentReport.

Provides format functions that produce different granularity outputs
depending on the target channel (CLI vs WeChat) and detail level.
"""

from __future__ import annotations

from butler.executors.agent_runner import AgentReport


def format_for_butler_tool_result(report: AgentReport, milestones: list[str] | None = None) -> dict:
    """Format a report as the tool result dict returned to Butler LLM.

    Only includes headline, changes, decisions, and issues — NOT the full summary.
    This prevents Butler from doing redundant re-summarization.
    """
    d: dict = {
        "headline": report.headline,
        "changes_count": len(report.changes),
    }
    if report.changes:
        d["changes"] = [
            {"file": c.file, "action": c.action, "desc": c.description}
            for c in report.changes[:15]
        ]
    if report.decisions:
        d["decisions"] = report.decisions[:5]
    if report.issues:
        d["issues"] = report.issues[:5]
    if milestones:
        d["execution_steps"] = len(milestones)
    return d


def format_for_cli(report: AgentReport) -> str:
    """Rich-friendly format for CLI: headline + changes + decisions + issues."""
    parts: list[str] = []

    parts.append(f"[bold]{report.headline}[/bold]")

    if report.changes:
        parts.append("")
        parts.append("[dim]变更文件:[/dim]")
        for c in report.changes:
            icon = {"created": "+", "modified": "~", "deleted": "-"}.get(c.action, "?")
            desc = f" — {c.description}" if c.description else ""
            parts.append(f"  {icon} {c.file}{desc}")

    if report.decisions:
        parts.append("")
        parts.append("[dim]关键决策:[/dim]")
        for d in report.decisions:
            parts.append(f"  - {d}")

    if report.issues:
        parts.append("")
        parts.append("[bold yellow]需关注:[/bold yellow]")
        for issue in report.issues:
            parts.append(f"  ! {issue}")

    return "\n".join(parts)


def format_for_wechat(report: AgentReport) -> str:
    """Compact format for WeChat: headline + file count + issues only."""
    parts: list[str] = [report.headline]

    if report.changes:
        action_counts: dict[str, int] = {}
        for c in report.changes:
            action_counts[c.action] = action_counts.get(c.action, 0) + 1
        summary_parts = []
        if action_counts.get("created"):
            summary_parts.append(f"新建{action_counts['created']}个文件")
        if action_counts.get("modified"):
            summary_parts.append(f"修改{action_counts['modified']}个文件")
        if action_counts.get("deleted"):
            summary_parts.append(f"删除{action_counts['deleted']}个文件")
        if summary_parts:
            parts.append("| " + "，".join(summary_parts))

    if report.issues:
        parts.append("")
        for issue in report.issues:
            parts.append(f"⚠ {issue}")

    parts.append("\n回复「详细」查看完整报告")
    return "\n".join(parts)


def format_detail(report: AgentReport, section: str = "") -> str:
    """Detailed view for /detail command. Section can be empty (=full), changes, decisions, log."""
    if section == "changes":
        if not report.changes:
            return "没有文件变更记录。"
        lines = ["文件变更详情:"]
        for c in report.changes:
            lines.append(f"  [{c.action}] {c.file}")
            if c.description:
                lines.append(f"         {c.description}")
        return "\n".join(lines)

    if section == "decisions":
        if not report.decisions:
            return "没有关键决策记录。"
        lines = ["关键决策:"]
        for i, d in enumerate(report.decisions, 1):
            lines.append(f"  {i}. {d}")
        return "\n".join(lines)

    if section == "issues":
        if not report.issues:
            return "没有需要关注的问题。"
        lines = ["需关注的问题:"]
        for issue in report.issues:
            lines.append(f"  - {issue}")
        return "\n".join(lines)

    # Default: full summary
    parts: list[str] = []
    if report.summary:
        parts.append(report.summary)
    else:
        parts.append(report.headline)

    if report.changes:
        parts.append("")
        parts.append(f"文件变更 ({len(report.changes)}):")
        for c in report.changes:
            icon = {"created": "+", "modified": "~", "deleted": "-"}.get(c.action, "?")
            desc = f" — {c.description}" if c.description else ""
            parts.append(f"  {icon} {c.file}{desc}")

    if report.decisions:
        parts.append("")
        parts.append("决策:")
        for i, d in enumerate(report.decisions, 1):
            parts.append(f"  {i}. {d}")

    if report.issues:
        parts.append("")
        parts.append("需关注:")
        for issue in report.issues:
            parts.append(f"  ! {issue}")

    return "\n".join(parts)
