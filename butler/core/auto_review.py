"""Lightweight auto-approval reviewer (Codex Guardian subset, fail-closed)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from butler.env_parse import env_truthy, int_env

_READ_ONLY_HINTS = re.compile(
    r"(?i)\b(git\s+(status|diff|log|show|branch)|pytest\s+--collect|ls\b|pwd\b|cat\s+|head\s+|tail\s+|wc\s+)",
)

_WRITE_HINTS = re.compile(
    r"(?i)\b(rm\b|curl\b|wget\b|chmod\b|chown\b|>\s|>>\s|tee\s+|patch\b|write_file|deploy)",
)


def auto_review_enabled() -> bool:
    return env_truthy("BUTLER_AUTO_REVIEW", default=False)


def max_denials_per_turn() -> int:
    import os

    try:
        return max(1, int_env("BUTLER_AUTO_REVIEW_MAX_DENIALS", 3))
    except ValueError:
        return 3


@dataclass(frozen=True)
class AutoReviewResult:
    allowed: bool
    reason: str = ""
    skipped: bool = False


def _turn_denial_count(diagnostics: dict[str, Any] | None) -> int:
    if not isinstance(diagnostics, dict):
        return 0
    return int(diagnostics.get("auto_review_denials") or 0)


def _record_denial(diagnostics: dict[str, Any] | None) -> None:
    if isinstance(diagnostics, dict):
        diagnostics["auto_review_denials"] = _turn_denial_count(diagnostics) + 1


def try_auto_review_terminal(
    command: str,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> AutoReviewResult:
    """
    Optional LLM reviewer for terminal approval. Default off.
    Never auto-allows write/network/danger patterns.
    """
    if not auto_review_enabled():
        return AutoReviewResult(allowed=False, skipped=True, reason="disabled")

    if _turn_denial_count(diagnostics) >= max_denials_per_turn():
        return AutoReviewResult(
            allowed=False,
            reason="auto_review denial budget exhausted",
            skipped=True,
        )

    text = (command or "").strip()
    if not text:
        return AutoReviewResult(allowed=False, skipped=True)

    if _WRITE_HINTS.search(text):
        _record_denial(diagnostics)
        return AutoReviewResult(allowed=False, reason="write_or_network_hint")

    from butler.core.auto_review_ops import (
        parse_auto_review_llm_response_safe,
        sandbox_read_only_auto_review_safe,
    )

    if sandbox_read_only_auto_review_safe(text, diagnostics=diagnostics):
        return AutoReviewResult(allowed=True, reason="sandboxed_read_only")

    if not _READ_ONLY_HINTS.search(text):
        _record_denial(diagnostics)
        return AutoReviewResult(allowed=False, reason="not_read_only_heuristic")

    from butler.core.auto_review_ops import run_auto_review_llm_safe

    parsed = run_auto_review_llm_safe(text, diagnostics=diagnostics)
    if parsed is not None:
        _allowed, reason = parsed
        return AutoReviewResult(allowed=True, reason=reason)

    _record_denial(diagnostics)
    return AutoReviewResult(allowed=False, reason="reviewer_fail_closed")


__all__ = [
    "AutoReviewResult",
    "auto_review_enabled",
    "max_denials_per_turn",
    "try_auto_review_terminal",
]
