"""Structured observability events — technical vs semantic layers (AP-5).

Parent events store hashes/digests only (no prompt bodies). Child events carry
tool names and retrieval modes for trajectory debugging.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from butler.core.metrics_sink import record_event


def prompt_hash_from_messages(messages: list[Any] | None) -> str:
    """Stable short hash of message shape (content hashed, not stored)."""
    rows: list[dict[str, Any]] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if isinstance(content, list):
            blob = json.dumps(content, sort_keys=True, default=str)
        else:
            blob = str(content or "")
        content_fp = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]
        rows.append({"role": role, "fp": content_fp})
    digest = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:16]


def args_digest(args: dict[str, Any] | None) -> str:
    try:
        blob = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except TypeError:
        blob = str(args or {})
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def emit_llm_api_call(
    *,
    duration_ms: float,
    status: str,
    provider: str = "",
    prompt_hash: str = "",
    token_in: int = 0,
    token_out: int = 0,
    session_key: str = "",
) -> None:
    record_event(
        "llm_api_call",
        {
            "duration_ms": round(float(duration_ms), 2),
            "status": str(status or "ok"),
            "provider": str(provider or "")[:32],
            "prompt_hash": str(prompt_hash or "")[:16],
            "token_in": max(0, int(token_in or 0)),
            "token_out": max(0, int(token_out or 0)),
            "ts": time.time(),
        },
        session_key=session_key,
    )


def emit_tool_action(
    *,
    tool_name: str,
    args_digest_value: str = "",
    outcome: str = "ok",
    session_key: str = "",
) -> None:
    record_event(
        "tool_action",
        {
            "tool_name": str(tool_name or "")[:64],
            "args_digest": str(args_digest_value or "")[:16],
            "outcome": str(outcome or "ok")[:32],
            "ts": time.time(),
        },
        session_key=session_key,
    )


def emit_retrieval(
    *,
    mode: str,
    degraded: bool = False,
    fallbacks: int = 0,
    session_key: str = "",
) -> None:
    record_event(
        "retrieval",
        {
            "mode": str(mode or "")[:48],
            "degraded": bool(degraded),
            "fallbacks": max(0, int(fallbacks or 0)),
            "ts": time.time(),
        },
        session_key=session_key,
    )


__all__ = [
    "args_digest",
    "emit_llm_api_call",
    "emit_retrieval",
    "emit_tool_action",
    "prompt_hash_from_messages",
]
