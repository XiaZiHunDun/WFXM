"""Inbound message queue best-effort helpers (P0-A)."""

from __future__ import annotations

import json
from collections.abc import Callable
import logging
import re
from pathlib import Path

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def record_queue_drop_telemetry(session_key: str, *, reason: str, count: int = 1) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_queue_drop
        from butler.ops.runtime_metrics import inc

        inc(
            "inbound_queue_drop",
            labels={"reason": reason[:24]},
            session_key=session_key,
            value=count,
        )
        record_queue_drop(session_key, reason, count)

    safe_best_effort(_run, label="message_queue.record_drop", default=None)


def record_queue_operation_safe(session_key: str, priority: str, body: str) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_queue_operation

        record_queue_operation(session_key, priority, body)

    safe_best_effort(_run, label="message_queue.record_operation", default=None)


def refresh_queue_gauges_safe(session_key: str, *, depth_fn: Callable[[str], int], total_fn: Callable[[], int]) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import set_gauge

        key = str(session_key or "default")
        set_gauge("inbound_queue_depth", float(depth_fn(key)), session_key=key)
        set_gauge("inbound_queue_depth_total", float(total_fn()))

    safe_best_effort(_run, label="message_queue.refresh_gauges", default=None)


def reset_queue_gauges_safe(
    *,
    session_key: str | None,
    refresh_fn: Callable[[str], None] | None = None,
) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import set_gauge

        if session_key is None:
            set_gauge("inbound_queue_depth_total", 0.0)
        elif refresh_fn is not None:
            refresh_fn(session_key)

    safe_best_effort(_run, label="message_queue.reset_gauges", default=None)


def persist_enqueue_loud(session_key: str, row: dict[str, object], *, persist_dir_fn: Callable[[], Path]) -> None:
    try:
        root = persist_dir_fn()
        root.mkdir(parents=True, exist_ok=True)
        safe_key = re.sub(r"[^\w\-]", "_", session_key)[:120]
        path = root / f"{safe_key}.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Queue persist write failed: %s", exc)


def persist_remove_loud(
    session_key: str,
    persist_id: str,
    *,
    persist_dir_fn: Callable[[], Path],
) -> None:
    try:
        root = persist_dir_fn()
        safe_key = re.sub(r"[^\w\-]", "_", session_key)[:120]
        path = root / f"{safe_key}.jsonl"
        if not path.is_file():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        marker = f'"id": "{persist_id}"'
        kept = [ln for ln in lines if marker not in ln]
        if len(kept) == len(lines):
            return
        if kept:
            from butler.io.atomic_write import atomic_write_text

            atomic_write_text(path, "\n".join(kept) + "\n")
        else:
            path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Queue persist remove failed: %s", exc)


def persist_clear_loud(
    session_key: str | None,
    *,
    persist_dir_fn: Callable[[], Path],
) -> None:
    try:
        root = persist_dir_fn()
        if not root.is_dir():
            return
        if session_key is None:
            for f in root.glob("*.jsonl"):
                f.unlink(missing_ok=True)
        else:
            safe_key = re.sub(r"[^\w\-]", "_", session_key)[:120]
            (root / f"{safe_key}.jsonl").unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Queue persist clear failed: %s", exc)


def queue_mode_suffix_safe(session_key: str) -> str:
    def _build() -> str:
        from butler.gateway.queue_settings import get_queue_mode

        mode = get_queue_mode(session_key)
        if mode != "followup":
            return f"（队列模式：{mode}）"
        return ""

    suffix = safe_best_effort(_build, label="message_queue.queue_mode", default="")
    return str(suffix or "")
