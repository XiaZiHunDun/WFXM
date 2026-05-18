"""Structured agent reports for Butler orchestration channels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Change:
    file: str
    action: str  # "created" | "modified" | "deleted"
    description: str


@dataclass
class AgentReport:
    headline: str = ""
    changes: list[Change] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    summary: str = ""
    success: bool = True
    iterations: int = 0
    tool_calls: int = 0
    tokens_used: int = 0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "changes": [
                {"file": c.file, "action": c.action, "description": c.description}
                for c in self.changes
            ],
            "decisions": list(self.decisions),
            "issues": list(self.issues),
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentReport:
        raw = dict(data or {})
        changes_raw = raw.pop("changes", []) or []
        changes: list[Change] = []
        for item in changes_raw:
            if isinstance(item, Change):
                changes.append(item)
                continue
            if not isinstance(item, dict):
                continue
            changes.append(
                Change(
                    file=str(item.get("file", "") or ""),
                    action=str(item.get("action", "") or ""),
                    description=str(item.get("description", item.get("desc", "")) or ""),
                )
            )
        return cls(
            headline=str(raw.get("headline", "") or ""),
            changes=changes,
            decisions=[str(x) for x in (raw.get("decisions") or [])],
            issues=[str(x) for x in (raw.get("issues") or [])],
            summary=str(raw.get("summary", "") or ""),
        )


def format_for_butler_tool_result(
    report: AgentReport,
    milestones: list[str] | None = None,
) -> dict[str, Any]:
    """Compact dict for Butler LLM — headline + changes + decisions."""
    d: dict[str, Any] = {
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
    """Rich markup format for CLI display (prompt_toolkit Rich tags)."""
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
    """Compact WeChat format with drilldown hint."""
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
    """Full detail for /detail command. Section can be empty (=full), changes, decisions, issues."""
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

    stats = []
    if report.iterations > 0:
        stats.append(f"{report.iterations} 轮")
    if report.tool_calls > 0:
        stats.append(f"{report.tool_calls} 工具调用")
    if report.tokens_used > 0:
        stats.append(f"{report.tokens_used:,} tokens")
    if report.elapsed_seconds > 0:
        stats.append(f"{report.elapsed_seconds:.1f}s")
    if stats:
        parts.append("")
        parts.append(f"执行统计: {' | '.join(stats)}")

    return "\n".join(parts)


_last_report: AgentReport | None = None


def cache_report(report: AgentReport) -> None:
    global _last_report
    _last_report = report


def get_last_report() -> AgentReport | None:
    return _last_report


__all__ = [
    "AgentReport", "Change",
    "format_detail", "format_for_butler_tool_result", "format_for_cli", "format_for_wechat",
    "cache_report", "get_last_report",
]
