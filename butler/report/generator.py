"""Structured agent reports for Butler orchestration channels."""

from __future__ import annotations

import re
from typing import Any, cast

from butler.report.acceptance_card import format_delegate_acceptance_card
from butler.report.generator_schema import (
    build_schema_repair_prompt,
    parse_structured_output,
    validate_structured_output,
)
from butler.report.report_types import AgentReport, Change

_DECISION_PATTERNS = (
    re.compile(r"\*\*\s*rating\s*\*\*\s*:\s*(approve|revise|block|keep|discard)\b", re.I),
    re.compile(r"\brating\s*:\s*(approve|revise|block|keep|discard)\b", re.I),
    re.compile(r"\bdecision\s*:\s*(approve|revise|block|keep|discard)\b", re.I),
    re.compile(r"\b(approve|revise|block|keep|discard)\b", re.I),
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


def enrich_output_schema(
    report: AgentReport,
    text: str,
    schema: dict[str, Any] | None,
) -> AgentReport:
    parsed = parse_structured_output(text, schema)
    if parsed:
        ok, errors = validate_structured_output(parsed, schema)
        if ok:
            report.structured_output = parsed
            for key, val in parsed.items():
                if str(key).lower() in ("rating", "decision", "verdict"):
                    report.decisions = list(
                        dict.fromkeys(list(report.decisions) + [str(val).lower()])
                    )
        else:
            report.structured_output = parsed
            repair = build_schema_repair_prompt(errors, schema)
            if repair:
                report.issues.append(repair[:500])
            for err in errors[:5]:
                report.issues.append(f"schema: {err}")
    return report


def _schema_validation_failed(report: AgentReport) -> bool:
    if any(str(i).startswith("schema:") for i in report.issues):
        return True
    if report.structured_output:
        return False
    return bool(report.issues)


def maybe_repair_structured_output(
    report: AgentReport,
    source_text: str,
    schema: dict[str, Any] | None,
    *,
    orchestrator: Any = None,
) -> AgentReport:
    """Multi-round LLM repair when schema validation failed (PR-X5 / 主线 N / P10)."""
    if not schema:
        return report
    from butler.report.generator_ops import (
        current_orchestrator_safe,
        output_schema_repair_settings_safe,
        schema_repair_round_loud,
    )

    settings = output_schema_repair_settings_safe()
    if settings is None:
        return report
    repair_enabled, validate_enabled, max_rounds = settings
    if not repair_enabled or not validate_enabled:
        return report
    if not _schema_validation_failed(report):
        ok, _ = validate_structured_output(report.structured_output, schema)
        if ok and report.structured_output:
            return report
    orchestrator = current_orchestrator_safe()
    if orchestrator is None:
        return report

    last_text = source_text or ""
    for _round in range(max_rounds):
        ok, _ = validate_structured_output(report.structured_output or {}, schema)
        if ok and report.structured_output:
            return report
        repair_prompt = build_schema_repair_prompt(
            [i for i in report.issues if str(i).startswith("schema:")],
            schema,
        )
        if not repair_prompt:
            repair_prompt = build_schema_repair_prompt(["structured output invalid"], schema)
        user_msg = f"{repair_prompt}\n\n---\n原始输出：\n{last_text[:12000]}"
        last_text, parsed, errs, repair_err = schema_repair_round_loud(
            orchestrator,
            user_msg,
            schema,
        )
        if repair_err:
            report.issues.append(f"schema_repair_error_r{_round + 1}: {repair_err}")
            break
        ok = bool(parsed) and not errs
        if ok and parsed:
            report.structured_output = parsed
            report.issues = [
                i for i in report.issues
                if not str(i).startswith("schema:")
                and "结构化输出未通过" not in str(i)
            ]
            for key, val in parsed.items():
                if str(key).lower() in ("rating", "decision", "verdict"):
                    report.decisions = list(
                        dict.fromkeys(list(report.decisions) + [str(val).lower()])
                    )
            return report
        if errs:
            report.issues.append(f"schema_repair_failed_r{_round + 1}: {errs[0]}")
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


def attach_delegate_task_times(report: AgentReport, task_id: str = "") -> AgentReport:
    """Fill created/completed ISO timestamps from runtime task store for WeChat push."""
    tid = str(task_id or report.task_id or "").strip()
    if not tid:
        return report
    from butler.report.generator_ops import attach_delegate_task_times_safe

    attach_delegate_task_times_safe(report, tid)
    return report


def _format_task_time(iso: str) -> str:
    """Compact local time for WeChat delegate push (Asia/Shanghai)."""
    from datetime import datetime, timezone

    raw = str(iso or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        from butler.report.generator_ops import format_task_time_shanghai_safe

        dt = format_task_time_shanghai_safe(dt)
        return str(dt.strftime("%m-%d %H:%M"))
    except ValueError:
        return raw[:16]


def format_for_wechat(report: AgentReport) -> str:
    """Compact WeChat format with drilldown hint."""
    parts: list[str] = [report.headline]

    time_bits: list[str] = []
    if report.task_created_at:
        time_bits.append(f"提交 {_format_task_time(report.task_created_at)}")
    if report.task_completed_at:
        time_bits.append(f"完成 {_format_task_time(report.task_completed_at)}")
    if time_bits:
        parts.append("⏱ " + " · ".join(time_bits))

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

    if report.decisions:
        parts.append("")
        parts.append("关键决策:")
        for d in report.decisions[:3]:
            parts.append(f"  * {d[:80]}")

    meta_parts: list[str] = []
    if report.task_id:
        meta_parts.append(f"任务 {report.task_id}")
    if report.iterations:
        meta_parts.append(f"迭代 {report.iterations} 轮")
    if report.changes:
        tool_count = len(report.changes)
        meta_parts.append(f"变更 {tool_count} 处")
    if meta_parts:
        parts.append(" · ".join(meta_parts) + " · 发 /任务 可查记录")
    if report.child_session_key:
        parts.append(f"子会话 {report.child_session_key}")

    if report.task_id or report.changes or (report.structured_output or {}).get("acceptance"):
        parts.append("")
        parts.append(format_delegate_acceptance_card(report))
    else:
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
    from butler.report.generator_ops import current_session_key_safe

    ctx_key = current_session_key_safe()
    if ctx_key:
        return str(ctx_key)
    return "default"


def cache_report(report: AgentReport, *, session_key: str = "") -> None:
    """Store the latest delegate/workflow report for a session (memory + disk)."""
    key = _resolve_report_key(session_key)
    _reports[key] = report
    from butler.report.generator_ops import persist_report_safe

    persist_report_safe(report, session_key=key)


def get_last_report(session_key: str = "") -> AgentReport | None:
    """Return the cached report for ``session_key`` (or current execution context)."""
    key = _resolve_report_key(session_key)
    cached = _reports.get(key)
    if cached is not None:
        return cached
    from butler.report.generator_ops import load_persisted_report_safe

    loaded = cast(AgentReport | None, load_persisted_report_safe(key))
    if loaded is not None:
        _reports[key] = loaded
    return loaded


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
    "attach_delegate_task_times",
    "build_schema_repair_prompt",
    "enrich_report_decisions",
    "maybe_repair_structured_output",
    "validate_structured_output",
    "format_detail",
    "format_for_butler_tool_result",
    "format_for_cli",
    "format_for_wechat",
    "parse_decisions_from_text",
    "cache_report",
    "clear_report_cache",
    "get_last_report",
]
