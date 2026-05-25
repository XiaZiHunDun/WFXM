"""Structured agent reports for Butler orchestration channels."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_DECISION_PATTERNS = (
    re.compile(r"\*\*\s*rating\s*\*\*\s*:\s*(approve|revise|block|keep|discard)\b", re.I),
    re.compile(r"\brating\s*:\s*(approve|revise|block|keep|discard)\b", re.I),
    re.compile(r"\bdecision\s*:\s*(approve|revise|block|keep|discard)\b", re.I),
    re.compile(r"\b(approve|revise|block|keep|discard)\b", re.I),
)


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
    task_preview: str = ""
    task_id: str = ""
    child_session_key: str = ""
    iterations: int = 0
    tool_calls: int = 0
    tokens_used: int = 0
    elapsed_seconds: float = 0.0
    failed_steps: list[str] = field(default_factory=list)
    step_outcomes: dict[str, str] = field(default_factory=dict)
    structured_output: dict[str, Any] = field(default_factory=dict)

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
            "success": self.success,
            "task_preview": self.task_preview,
            "task_id": self.task_id,
            "child_session_key": self.child_session_key,
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "tokens_used": self.tokens_used,
            "elapsed_seconds": self.elapsed_seconds,
            "failed_steps": list(self.failed_steps),
            "step_outcomes": dict(self.step_outcomes),
            "structured_output": dict(self.structured_output),
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
            success=bool(raw.get("success", True)),
            task_preview=str(raw.get("task_preview", "") or ""),
            task_id=str(raw.get("task_id", "") or ""),
            child_session_key=str(raw.get("child_session_key", "") or ""),
            failed_steps=[str(x) for x in (raw.get("failed_steps") or [])],
            step_outcomes={
                str(k): str(v)
                for k, v in (raw.get("step_outcomes") or {}).items()
                if isinstance(raw.get("step_outcomes"), dict)
            },
            structured_output=dict(raw.get("structured_output") or {}),
        )


def parse_decisions_from_text(text: str) -> list[str]:
    """Deterministic enum extraction (TradingAgents SignalProcessor subset)."""
    blob = str(text or "")
    if not blob.strip():
        return []
    found: list[str] = []
    seen: set[str] = set()
    for pat in _DECISION_PATTERNS:
        for m in pat.finditer(blob):
            val = str(m.group(1) or "").strip().lower()
            if val and val not in seen:
                seen.add(val)
                found.append(val)
    return found[:8]


def enrich_report_decisions(report: AgentReport, text: str) -> AgentReport:
    parsed = parse_decisions_from_text(text)
    if not parsed:
        return report
    merged = list(dict.fromkeys(list(report.decisions) + parsed))
    report.decisions = merged
    return report


def parse_structured_output(text: str, schema: dict[str, Any] | None) -> dict[str, Any]:
    """Extract JSON object from final text when workflow declares output_schema."""
    if not schema:
        return {}
    blob = str(text or "").strip()
    if not blob:
        return {}
    import json
    import re

    candidates: list[dict[str, Any]] = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", blob, re.DOTALL)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            if isinstance(parsed, dict):
                candidates.append(parsed)
        except json.JSONDecodeError:
            pass
    for m in re.finditer(r"\{[^{}]*\}", blob):
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                candidates.append(parsed)
        except json.JSONDecodeError:
            continue
    fields = schema.get("fields") if isinstance(schema.get("fields"), list) else []
    if not fields and isinstance(schema, dict):
        fields = [k for k in schema.keys() if k not in ("type", "fields")]
    if not candidates:
        return {}
    best = candidates[-1]
    if fields:
        return {k: best.get(k) for k in fields if k in best}
    return dict(best)


def enrich_output_schema(
    report: AgentReport,
    text: str,
    schema: dict[str, Any] | None,
) -> AgentReport:
    parsed = parse_structured_output(text, schema)
    if parsed:
        report.structured_output = parsed
        for key, val in parsed.items():
            if str(key).lower() in ("rating", "decision", "verdict"):
                report.decisions = list(
                    dict.fromkeys(list(report.decisions) + [str(val).lower()])
                )
    return report


def render_structured_output_markdown(data: dict[str, Any]) -> str:
    if not data:
        return ""
    lines = ["## 结构化终局"]
    for key, val in data.items():
        lines.append(f"- **{key}**: {val}")
    return "\n".join(lines)


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

    if not report.success:
        parts[0] = report.headline or "任务未完成"

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
        for issue in report.issues[:3]:
            parts.append(f"⚠ {issue}")

    if not report.success and not report.issues:
        parts.append("")
        parts.append("⚠ 工具执行未成功，请发 /详细 查看原因")

    if report.task_id:
        parts.append(f"任务 {report.task_id} · 发 /任务 可查记录")
    if report.child_session_key:
        parts.append(f"子会话 {report.child_session_key}")
    parts.append("\n回复「/详细」或「详细」查看完整报告")
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
    if report.task_id:
        parts.append(f"任务 ID: {report.task_id}")
    if report.child_session_key:
        parts.append(f"子会话: {report.child_session_key}")
    if report.task_preview:
        parts.append(f"【本报告任务】{report.task_preview}")
        parts.append("")
    if not report.success:
        parts.append(report.headline or "任务未完成")
        parts.append("")
    if report.summary:
        parts.append(report.summary)
    elif report.headline:
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

    if report.step_outcomes:
        parts.append("")
        parts.append("工作流步骤:")
        for step_id, outcome in report.step_outcomes.items():
            label = {
                "ok": "成功",
                "fail": "失败",
                "approval_pending": "待确认",
            }.get(outcome, outcome)
            parts.append(f"  - {step_id}: {label}")
        if report.failed_steps:
            parts.append(f"  失败/等待: {', '.join(report.failed_steps)}")

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


_reports: dict[str, AgentReport] = {}


def _resolve_report_key(session_key: str | None = None) -> str:
    key = str(session_key or "").strip()
    if key:
        return key
    try:
        from butler.execution_context import get_current_session_key

        ctx_key = str(get_current_session_key() or "").strip()
        if ctx_key:
            return ctx_key
    except Exception:
        pass
    return "default"


def cache_report(report: AgentReport, *, session_key: str = "") -> None:
    """Store the latest delegate/workflow report for a session (memory + disk)."""
    key = _resolve_report_key(session_key)
    _reports[key] = report
    try:
        from butler.report_store import persist_report

        persist_report(report, session_key=key, task_id=report.task_id)
    except Exception:
        pass


def get_last_report(session_key: str = "") -> AgentReport | None:
    """Return the cached report for ``session_key`` (or current execution context)."""
    key = _resolve_report_key(session_key)
    cached = _reports.get(key)
    if cached is not None:
        return cached
    try:
        from butler.report_store import load_persisted_report

        loaded = load_persisted_report(key)
        if loaded is not None:
            _reports[key] = loaded
        return loaded
    except Exception:
        return None


def clear_report_cache(session_key: str = "") -> None:
    """Reset cached report for one session, or all sessions when ``session_key`` is empty."""
    key = str(session_key or "").strip()
    if not key:
        _reports.clear()
        return
    _reports.pop(_resolve_report_key(key), None)


__all__ = [
    "AgentReport",
    "Change",
    "enrich_report_decisions",
    "format_detail",
    "format_for_butler_tool_result",
    "format_for_cli",
    "format_for_wechat",
    "parse_decisions_from_text",
    "cache_report",
    "clear_report_cache",
    "get_last_report",
]
