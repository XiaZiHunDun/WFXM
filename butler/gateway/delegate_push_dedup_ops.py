"""Delegate push dedup best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def task_completed_epoch_safe(task_id: str) -> float | None:
    tid = str(task_id or "").strip()
    if not tid:
        return None

    def _run() -> float:
        from datetime import datetime, timezone

        from butler.runtime.task_store import get_task

        row = get_task(tid)
        if not isinstance(row, dict):
            raise ValueError("task row missing")
        if str(row.get("status") or "") not in ("completed", "failed"):
            raise ValueError("task not terminal")
        raw = str(row.get("updated_at") or row.get("created_at") or "").strip()
        if not raw:
            raise ValueError("task timestamp missing")
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(dt.timestamp())

    result = safe_best_effort(
        _run,
        label="delegate_push_dedup.task_epoch",
        default=None,
    )
    return float(result) if isinstance(result, (int, float)) else None


def flush_deferred_pushes_safe(
    chat_id: str,
    items: list[tuple[str, str]],
    *,
    bridge: Any | None,
) -> None:
    def _run() -> None:
        if bridge is None or str(getattr(bridge, "chat_id", "") or "") != chat_id:
            from butler.gateway.delegate_push_dedup import _schedule_deferred_push_standalone

            for body, kind in items:
                _schedule_deferred_push_standalone(chat_id, body, kind=kind)
            return
        from butler.gateway.delegate_push_dedup import should_deliver_delegate_push

        for body, kind in items:
            if kind == "delegate":
                ok, reason = should_deliver_delegate_push(chat_id, "", body=body)
                if not ok:
                    logger.info(
                        "deferred delegate push suppressed chat=%s reason=%s",
                        chat_id[:12],
                        reason,
                    )
                    continue
            bridge.schedule_completion_push(body, kind=kind)

    safe_best_effort(_run, label="delegate_push_dedup.flush", default=None)


def push_standalone_deferred_safe(chat_id: str, body: str) -> None:
    def _run() -> None:
        from butler.runtime.notify import push_runtime_message

        from butler.gateway.delegate_push_dedup import (
            mark_delegate_push_delivered,
            should_deliver_delegate_push,
        )

        ok, reason = should_deliver_delegate_push(chat_id, "", body=body)
        if not ok:
            logger.info(
                "deferred delegate push suppressed chat=%s reason=%s",
                chat_id[:12],
                reason,
            )
            return
        if push_runtime_message("[Butler] 委派完成", body):
            mark_delegate_push_delivered(chat_id, "", body=body)

    safe_best_effort(_run, label="delegate_push_dedup.standalone_push", default=None)
