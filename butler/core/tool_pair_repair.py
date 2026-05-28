"""Repair missing tool_result messages after compaction (OMO tool-pair-validator subset)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

PLACEHOLDER_CONTENT = "Tool output unavailable (context compacted)"


def tool_pair_repair_enabled() -> bool:
    raw = os.getenv("BUTLER_TOOL_PAIR_REPAIR", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def repair_tool_pairs(
    messages: list[dict],
    *,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[list[dict], int]:
    """Insert synthetic tool messages for assistant tool_calls lacking tool results."""
    if not tool_pair_repair_enabled() or not messages:
        return messages, 0

    out: list[dict] = []
    repairs = 0
    pending: list[dict] = []

    def flush_pending() -> None:
        nonlocal repairs
        for tc in pending:
            tc_id = str(tc.get("id") or "").strip()
            if not tc_id:
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = str(fn.get("name") or "tool")
            out.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "name": name,
                "content": PLACEHOLDER_CONTENT,
                "_butler_synthetic_tool_result": True,
            })
            repairs += 1
        pending.clear()

    for msg in messages:
        if not isinstance(msg, dict):
            flush_pending()
            out.append(msg)
            continue
        role = msg.get("role")
        if role == "assistant":
            flush_pending()
            out.append(msg)
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict) and tc.get("id"):
                    pending.append(tc)
        elif role == "tool":
            tc_id = str(msg.get("tool_call_id") or "")
            if tc_id:
                pending = [t for t in pending if str(t.get("id") or "") != tc_id]
            out.append(msg)
        else:
            flush_pending()
            out.append(msg)

    flush_pending()

    if repairs and diagnostics is not None:
        diagnostics["tool_pair_repair_count"] = int(
            diagnostics.get("tool_pair_repair_count", 0) or 0
        ) + repairs
        diagnostics["loop_transition_reason"] = "tool_pair_repair"
        try:
            from butler.core.session_transcript import record_generic_event

            record_generic_event(
                str(diagnostics.get("session_key") or ""),
                "tool_pair_repair",
                {"count": repairs},
            )
        except Exception as exc:
            logger.debug("flush pending skipped: %s", exc)
        logger.debug("Tool-pair repair inserted %d synthetic tool results", repairs)

    return out, repairs


def repair_tool_pairs_json_safe(messages: list[dict], **kwargs: Any) -> tuple[list[dict], int]:
    """Run repair; ensure synthetic markers are JSON-serializable for API."""
    repaired, count = repair_tool_pairs(messages, **kwargs)
    for msg in repaired:
        if msg.get("_butler_synthetic_tool_result"):
            msg.pop("_butler_synthetic_tool_result", None)
    return repaired, count
