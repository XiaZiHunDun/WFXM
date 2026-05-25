"""Gateway hygiene preflight helpers for long-lived AgentLoop sessions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from butler.core.context_budget import (
    calculate_token_warning_state,
    compact_circuit_open,
    get_auto_compact_threshold,
    is_auto_compact_enabled,
)

logger = logging.getLogger(__name__)


@dataclass
class HygienePreflightResult:
    messages: list[dict]
    compressed: bool = False


def run_hygiene_preflight(
    messages: list[dict],
    *,
    max_context_tokens: int,
    diagnostics: dict[str, Any],
    estimate_tokens: Callable[[list[dict]], int],
    compress: Callable[..., list[dict]],
    threshold_ratio: float = 0.85,
    hard_message_limit: int = 400,
    consecutive_compact_failures: int = 0,
    max_output_tokens: int | None = None,
) -> HygienePreflightResult:
    """Return possibly compressed messages and update diagnostics in-place."""
    del threshold_ratio  # legacy param; threshold follows Claude Code autoCompact

    for key in list(diagnostics):
        if str(key).startswith(("hygiene_", "context_")):
            diagnostics.pop(key, None)

    diagnostics.update({
        "hygiene_checked": True,
        "hygiene_compressed": False,
        "hygiene_messages_before": len(messages),
        "context_compact_consecutive_failures": consecutive_compact_failures,
    })
    if len(messages) < 4:
        return HygienePreflightResult(messages=messages, compressed=False)

    estimated = estimate_tokens(messages)
    auto_threshold = get_auto_compact_threshold(
        max_context_tokens,
        max_output_tokens=max_output_tokens,
    )
    diagnostics.update(
        calculate_token_warning_state(
            estimated,
            max_context_tokens=max_context_tokens,
            max_output_tokens=max_output_tokens,
        )
    )
    diagnostics.update({
        "hygiene_estimated_tokens": estimated,
        "hygiene_threshold_tokens": auto_threshold,
    })

    circuit_open = compact_circuit_open(
        consecutive_compact_failures,
        max_context_tokens=max_context_tokens,
    )
    diagnostics["context_compact_circuit_open"] = circuit_open
    if circuit_open:
        diagnostics["hygiene_compact_skipped"] = "circuit_breaker"
        return HygienePreflightResult(messages=messages, compressed=False)

    token_limit_hit = (
        is_auto_compact_enabled()
        and estimated >= auto_threshold
    )
    hard_limit_hit = len(messages) >= hard_message_limit
    if not token_limit_hit and not hard_limit_hit:
        return HygienePreflightResult(messages=messages, compressed=False)

    compression_threshold = 0.0
    before_tokens = estimated
    try:
        from butler.execution_context import get_audit_session_key
        from butler.core.session_transcript import record_compact_scheduled

        record_compact_scheduled(
            get_audit_session_key(fallback="_global"),
            source="hygiene",
            messages_before=len(messages),
            tokens_estimated=before_tokens,
        )
    except Exception:
        pass
    try:
        compressed = compress(
            messages,
            threshold_ratio=compression_threshold,
            min_messages_to_compress=4,
            head_count=1,
            max_tail_messages=1,
            min_tail_messages=1,
        )
    except Exception as exc:
        failures = consecutive_compact_failures + 1
        diagnostics["context_compact_consecutive_failures"] = failures
        diagnostics["context_compact_circuit_open"] = compact_circuit_open(
            failures,
            max_context_tokens=max_context_tokens,
        )
        diagnostics["hygiene_compact_failed"] = True
        diagnostics["hygiene_compact_error"] = str(exc)[:500]
        logger.warning("Hygiene compact raised: %s", exc)
        return HygienePreflightResult(messages=messages, compressed=False)

    after_tokens = estimate_tokens(compressed)
    did_shrink = compressed is not messages and (
        len(compressed) < len(messages) or after_tokens < before_tokens - 50
    )

    if not did_shrink:
        diagnostics["hygiene_compact_noop"] = True
        diagnostics.pop("hygiene_compact_failed", None)
        return HygienePreflightResult(messages=messages, compressed=False)

    diagnostics.pop("hygiene_compact_noop", None)
    diagnostics["context_compact_consecutive_failures"] = 0
    diagnostics["context_compact_circuit_open"] = False
    diagnostics.update({
        "hygiene_compressed": True,
        "hygiene_messages_after": len(compressed),
        "hygiene_estimated_tokens_after": after_tokens,
    })
    try:
        from butler.execution_context import get_audit_session_key
        from butler.core.session_transcript import record_compact_done

        record_compact_done(
            get_audit_session_key(fallback="_global"),
            source="hygiene",
            messages_after=len(compressed),
            tokens_after=after_tokens,
        )
    except Exception:
        pass
    diagnostics.update(
        calculate_token_warning_state(
            after_tokens,
            max_context_tokens=max_context_tokens,
            max_output_tokens=max_output_tokens,
        )
    )
    return HygienePreflightResult(messages=compressed, compressed=True)
