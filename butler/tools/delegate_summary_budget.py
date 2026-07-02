"""Truncate delegate summaries before injecting into parent context."""

from __future__ import annotations

import json
import os
from typing import Any

from butler.env_parse import float_env, int_env


def delegate_summary_max_chars() -> int:
    return int_env("BUTLER_DELEGATE_SUMMARY_MAX_CHARS", 4000, min=500, max=50000)


def delegate_summary_reserve_ratio() -> float:
    return float_env("BUTLER_DELEGATE_SUMMARY_RESERVE_RATIO", 0.0, min=0.0, max=0.5)


def truncate_delegate_summary(text: str, *, max_chars: int | None = None) -> str:
    """Keep structured prefix lines when truncating long delegate prose."""
    cap = max_chars if max_chars is not None else delegate_summary_max_chars()
    body = (text or "").strip()
    if len(body) <= cap:
        return body
    head = body[: max(200, cap // 3)]
    tail_budget = cap - len(head) - 80
    if tail_budget < 100:
        return body[:cap] + "\n…[truncated]"
    return head + "\n…\n" + body[-tail_budget:] + "\n…[truncated]"


def budget_delegate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply headroom budget to delegate tool result payload."""
    out = dict(payload)
    summary = str(out.get("summary") or "")
    if summary:
        out["summary"] = truncate_delegate_summary(summary)
        if len(summary) > len(out["summary"]):
            out["summary_truncated"] = True
    return out


__all__ = [
    "budget_delegate_payload",
    "delegate_summary_max_chars",
    "delegate_summary_reserve_ratio",
    "truncate_delegate_summary",
]
