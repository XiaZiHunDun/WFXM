"""Report generator best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from butler.core.best_effort import safe_best_effort

from butler.core.meta_flags import output_schema_validate_enabled
from butler.core.confirm_flags import (
    output_schema_repair_enabled,
    output_schema_repair_max_rounds,
)
from butler.execution_context import (
    get_current_orchestrator,
    get_current_session_key,
)
from butler.runtime.task_store import get_task

logger = logging.getLogger(__name__)


def output_schema_validate_enabled_safe() -> bool | None:
    def _run() -> bool:

        return bool(output_schema_validate_enabled())

    return safe_best_effort(_run, label="generator.output_schema_validate", default=None)


def output_schema_repair_settings_safe() -> tuple[bool, bool, int] | None:
    """Return (repair_enabled, validate_enabled, max_rounds) or None if unavailable."""

    def _run() -> tuple[bool, bool, int]:

        return (
            bool(output_schema_repair_enabled()),
            bool(output_schema_validate_enabled()),
            int(output_schema_repair_max_rounds()),
        )

    return safe_best_effort(_run, label="generator.output_schema_repair_settings", default=None)


def current_orchestrator_safe() -> Any | None:
    def _run() -> Any:

        return get_current_orchestrator()

    return safe_best_effort(_run, label="generator.current_orchestrator", default=None)


def pydantic_validate_loud(data: dict[str, Any], specs: list[dict[str, Any]]) -> list[str]:
    """Return error strings; empty list means success."""
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
        return []
    except Exception as exc:
        return [f"pydantic: {exc}"]
    return []


def attach_delegate_task_times_safe(report: Any, task_id: str) -> None:
    def _run() -> None:

        rec = get_task(task_id)
        if rec:
            report.task_created_at = str(rec.get("created_at") or "")
            report.task_completed_at = str(rec.get("updated_at") or "")
        if not report.task_completed_at:
            report.task_completed_at = datetime.now(timezone.utc).isoformat()

    safe_best_effort(_run, label="generator.attach_task_times", default=None)


def format_task_time_shanghai_safe(dt: datetime) -> datetime:
    def _run() -> datetime:
        from zoneinfo import ZoneInfo

        return dt.astimezone(ZoneInfo("Asia/Shanghai"))

    result = safe_best_effort(_run, label="generator.task_time_tz", default=dt)
    return result if isinstance(result, datetime) else dt


def current_session_key_safe() -> str:
    def _run() -> str:

        return str(get_current_session_key() or "").strip()

    result = safe_best_effort(_run, label="generator.session_key", default="")
    return str(result or "")


def persist_report_safe(report: Any, *, session_key: str) -> None:
    def _run() -> None:
        from butler.report.store import persist_report

        persist_report(report, session_key=session_key, task_id=report.task_id)

    safe_best_effort(_run, label="generator.persist_report", default=None)


def load_persisted_report_safe(session_key: str) -> Any | None:
    def _run() -> Any:
        from butler.report.store import load_persisted_report

        return load_persisted_report(session_key)

    return safe_best_effort(_run, label="generator.load_report", default=None)


def schema_repair_round_loud(
    orchestrator: Any,
    user_msg: str,
    schema: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None, list[str], str | None]:
    """Run one LLM repair round; return (last_text, parsed, errors, error_message)."""
    try:
        from butler.report.generator import parse_structured_output, validate_structured_output
        from butler.transport.types import NormalizedResponse

        client = orchestrator.create_llm_client("butler")
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
            return user_msg, None, [], "invalid_llm_response"
        last_text = str(resp.content or "")
        ok, errs = validate_structured_output(parsed, schema)
        if ok and parsed:
            return last_text, parsed, [], None
        return last_text, parsed if parsed else None, list(errs), None
    except Exception as exc:
        return user_msg, None, [], str(exc)
