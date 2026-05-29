"""Structured agent reports for Butler orchestration channels."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
import logging

logger = logging.getLogger(__name__)

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
    field_names: list[str] = []
    raw_fields = schema.get("fields") if isinstance(schema.get("fields"), list) else []
    for item in raw_fields:
        if isinstance(item, str):
            field_names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            field_names.append(str(item["name"]))
    if not field_names and isinstance(schema, dict):
        field_names = [
            k for k in schema.keys() if k not in ("type", "fields", "title", "description")
        ]
    if not candidates:
        return {}
    best = candidates[-1]
    if field_names:
        return {k: best.get(k) for k in field_names if k in best}
    return dict(best)


def _schema_field_specs(schema: dict[str, Any]) -> list[dict[str, Any]]:
    fields = schema.get("fields")
    if isinstance(fields, list):
        specs: list[dict[str, Any]] = []
        for item in fields:
            if isinstance(item, str):
                specs.append({"name": item, "type": "string", "required": True})
            elif isinstance(item, dict) and item.get("name"):
                specs.append(dict(item))
        return specs
    specs = []
    for key, val in schema.items():
        if key in ("type", "fields", "title", "description"):
            continue
        if isinstance(val, dict):
            specs.append({"name": key, **val})
        else:
            specs.append({"name": key, "type": "string", "required": True})
    return specs


def validate_structured_output(
    data: dict[str, Any],
    schema: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Validate parsed output against a lightweight schema (optional Pydantic)."""
    if not schema:
        return True, []
    try:
        from butler.core.meta_flags import output_schema_validate_enabled

        if not output_schema_validate_enabled():
            return True, []
    except Exception as exc:
        logger.debug("validate structured output skipped: %s", exc)
    specs = _schema_field_specs(schema)
    if not specs:
        return True, []
    errors: list[str] = []
    for spec in specs:
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        required = bool(spec.get("required", True))
        if required and name not in data:
            errors.append(f"missing required field: {name}")
            continue
        if name not in data:
            continue
        val = data[name]
        expected = str(spec.get("type") or "string").strip().lower()
        if expected in ("str", "string") and not isinstance(val, str):
            errors.append(f"{name}: expected string")
        elif expected in ("int", "integer") and not isinstance(val, int):
            errors.append(f"{name}: expected integer")
        elif expected in ("bool", "boolean") and not isinstance(val, bool):
            errors.append(f"{name}: expected boolean")
        enum = spec.get("enum")
        if isinstance(enum, list) and enum and str(val) not in [str(x) for x in enum]:
            errors.append(f"{name}: value not in enum")
    if errors:
        return False, errors
    try:
        from pydantic import Field, create_model

        fields: dict[str, Any] = {}
        for spec in specs:
            name = str(spec["name"])
            required = bool(spec.get("required", True))
            expected = str(spec.get("type") or "string").lower()
            py_type: Any = str
            if expected in ("int", "integer"):
                py_type = int
            elif expected in ("bool", "boolean"):
                py_type = bool
            if required:
                fields[name] = (py_type, Field(...))
            else:
                fields[name] = (py_type | None, None)
        if fields:
            model = create_model("ButlerOutputSchema", **fields)
            model.model_validate(data)
    except ImportError:
        pass
    except Exception as exc:
        return False, [f"pydantic: {exc}"]
    return True, []


def build_schema_repair_prompt(
    errors: list[str],
    schema: dict[str, Any] | None,
) -> str:
    if not errors:
        return ""
    fields = [str(s.get("name") or "") for s in _schema_field_specs(schema or {}) if s.get("name")]
    return (
        "结构化输出未通过校验，请仅输出一个 JSON 对象修正以下问题：\n"
        + "\n".join(f"- {e}" for e in errors[:8])
        + (f"\n期望字段: {', '.join(fields)}" if fields else "")
    )


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
    try:
        from butler.core.confirm_flags import (
            output_schema_repair_enabled,
            output_schema_repair_max_rounds,
        )
        from butler.core.meta_flags import output_schema_validate_enabled

        if not output_schema_repair_enabled() or not output_schema_validate_enabled():
            return report
        max_rounds = output_schema_repair_max_rounds()
    except Exception:
        return report
    if not _schema_validation_failed(report):
        ok, _ = validate_structured_output(report.structured_output, schema)
        if ok and report.structured_output:
            return report
    if orchestrator is None:
        try:
            from butler.execution_context import get_current_orchestrator

            orchestrator = get_current_orchestrator()
        except Exception:
            orchestrator = None
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
        try:
            client = orchestrator.create_llm_client("butler")
            from butler.transport.types import NormalizedResponse

            resp = client.complete(
                messages=[
                    {
                        "role": "system",
                        "content": "你只输出一个 JSON 对象，不要 markdown 围栏或解释。",
                    },
                    {"role": "user", "content": user_msg},
                ],
                tools=None,
            )
            if not isinstance(resp, NormalizedResponse):
                break
            last_text = str(resp.content or "")
            parsed = parse_structured_output(last_text, schema)
            ok, errs = validate_structured_output(parsed, schema)
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
        except Exception as exc:
            report.issues.append(f"schema_repair_error_r{_round + 1}: {exc}")
            break
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
    except Exception as exc:
        logger.debug("resolve report key skipped: %s", exc)
    return "default"


def cache_report(report: AgentReport, *, session_key: str = "") -> None:
    """Store the latest delegate/workflow report for a session (memory + disk)."""
    key = _resolve_report_key(session_key)
    _reports[key] = report
    try:
        from butler.report.store import persist_report

        persist_report(report, session_key=key, task_id=report.task_id)
    except Exception as exc:
        logger.debug("cache report skipped: %s", exc)
def get_last_report(session_key: str = "") -> AgentReport | None:
    """Return the cached report for ``session_key`` (or current execution context)."""
    key = _resolve_report_key(session_key)
    cached = _reports.get(key)
    if cached is not None:
        return cached
    try:
        from butler.report.store import load_persisted_report

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
