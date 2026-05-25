"""Workflow lifecycle callbacks (Ansible handlers subset)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class WorkflowCallbackContext:
    workflow_name: str
    session_key: str = ""
    workspace: Path | None = None
    success: bool = False
    summary: str = ""
    step_outcomes: dict[str, str] = field(default_factory=dict)


WorkflowCallbackFn = Callable[[str, WorkflowCallbackContext], None]


def _parse_handlers(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
        elif isinstance(item, str) and item.strip():
            out.append({"type": item.strip()})
    return out


def register_builtin_callbacks() -> dict[str, WorkflowCallbackFn]:
    return {
        "notify": _cb_notify,
        "notify_wechat": _cb_notify,
        "ledger": _cb_ledger,
        "log": _cb_log,
    }


def _cb_notify(event: str, ctx: WorkflowCallbackContext) -> None:
    try:
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional
        from butler.report import AgentReport

        bridge = get_gateway_bridge_optional()
        if bridge is None:
            return
        report = AgentReport(
            headline=f"工作流 {ctx.workflow_name}（{event}）",
            summary=ctx.summary[:2000],
            success=ctx.success,
            step_outcomes=dict(ctx.step_outcomes),
        )
        bridge.notify_workflow_finished(report)
    except Exception as exc:
        logger.debug("workflow notify handler: %s", exc)


def _cb_ledger(event: str, ctx: WorkflowCallbackContext) -> None:
    if ctx.workspace is None:
        return
    path = Path(ctx.workspace) / ".butler" / "workflow_ledger.jsonl"
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "workflow": ctx.workflow_name,
        "success": ctx.success,
        "session_key": ctx.session_key,
        "step_outcomes": dict(ctx.step_outcomes),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("workflow ledger handler: %s", exc)


def _cb_log(event: str, ctx: WorkflowCallbackContext) -> None:
    logger.info(
        "workflow %s %s success=%s session=%s",
        ctx.workflow_name,
        event,
        ctx.success,
        ctx.session_key,
    )


def run_workflow_handlers(
    handlers: list[dict[str, Any]],
    *,
    event: str,
    ctx: WorkflowCallbackContext,
) -> None:
    registry = register_builtin_callbacks()
    for spec in handlers:
        typ = str(spec.get("type") or spec.get("handler") or "").strip().lower()
        fn = registry.get(typ)
        if fn is None:
            continue
        try:
            fn(event, ctx)
        except Exception as exc:
            logger.warning("workflow handler %s failed: %s", typ, exc)


__all__ = [
    "WorkflowCallbackContext",
    "run_workflow_handlers",
    "_parse_handlers",
]
