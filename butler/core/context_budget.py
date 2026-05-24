"""Context token budgeting (aligned with Claude Code autoCompact.ts thresholds)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

# Claude Code v2.1.88 defaults (services/compact/autoCompact.ts)
_MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000
_AUTOCOMPACT_BUFFER_TOKENS = 13_000
_WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
_ERROR_THRESHOLD_BUFFER_TOKENS = 20_000
_MANUAL_COMPACT_BUFFER_TOKENS = 3_000


@dataclass(frozen=True)
class ContextBudgetThresholds:
    """Computed thresholds for one model context size."""

    max_context_tokens: int
    effective_context_tokens: int
    auto_compact_at_tokens: int
    warn_at_tokens: int
    error_at_tokens: int
    blocking_at_tokens: int
    max_consecutive_compact_failures: int


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default)).strip() or default))
    except ValueError:
        return default


def get_output_reserve_tokens(*, max_output_tokens: int | None = None) -> int:
    """Tokens reserved for model output during compaction (CC: min(maxOutput, 20k))."""
    cap = _int_env("BUTLER_CONTEXT_OUTPUT_RESERVE", _MAX_OUTPUT_TOKENS_FOR_SUMMARY)
    if max_output_tokens is not None and max_output_tokens > 0:
        return min(max_output_tokens, cap)
    return cap


def get_effective_context_window(
    max_context_tokens: int,
    *,
    max_output_tokens: int | None = None,
) -> int:
    raw = max(1000, int(max_context_tokens or 128_000))
    reserved = get_output_reserve_tokens(max_output_tokens=max_output_tokens)
    return max(1000, raw - reserved)


def get_auto_compact_threshold(
    max_context_tokens: int,
    *,
    max_output_tokens: int | None = None,
) -> int:
    effective = get_effective_context_window(
        max_context_tokens,
        max_output_tokens=max_output_tokens,
    )
    buffer = _int_env("BUTLER_CONTEXT_COMPACT_RESERVE", _AUTOCOMPACT_BUFFER_TOKENS)
    candidate = effective - buffer
    # CC formula assumes 100k+ windows; tiny test/sandbox configs fall back to 85%.
    ratio_floor = int(effective * 0.85)
    if candidate < ratio_floor:
        return max(100, ratio_floor)
    return candidate


def load_context_thresholds(
    max_context_tokens: int,
    *,
    max_output_tokens: int | None = None,
) -> ContextBudgetThresholds:
    max_tok = max(1000, int(max_context_tokens or 128_000))
    effective = get_effective_context_window(max_tok, max_output_tokens=max_output_tokens)
    auto_at = get_auto_compact_threshold(max_tok, max_output_tokens=max_output_tokens)
    warn_buf = _int_env("BUTLER_CONTEXT_WARNING_BUFFER", _WARNING_THRESHOLD_BUFFER_TOKENS)
    err_buf = _int_env("BUTLER_CONTEXT_ERROR_BUFFER", _ERROR_THRESHOLD_BUFFER_TOKENS)
    block_buf = _int_env("BUTLER_CONTEXT_BLOCKING_BUFFER", _MANUAL_COMPACT_BUFFER_TOKENS)
    return ContextBudgetThresholds(
        max_context_tokens=max_tok,
        effective_context_tokens=effective,
        auto_compact_at_tokens=auto_at,
        warn_at_tokens=max(0, auto_at - warn_buf),
        error_at_tokens=max(0, auto_at - err_buf),
        blocking_at_tokens=max(0, effective - block_buf),
        max_consecutive_compact_failures=_int_env(
            "BUTLER_CONTEXT_COMPACT_MAX_FAILURES",
            3,
        ),
    )


def is_auto_compact_enabled() -> bool:
    flag = os.getenv("BUTLER_DISABLE_AUTO_COMPACT", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return False
    if os.getenv("BUTLER_DISABLE_COMPACT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    return True


def calculate_token_warning_state(
    estimated_tokens: int,
    *,
    max_context_tokens: int,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """Mirror Claude Code ``calculateTokenWarningState`` flags + Butler tier labels."""
    thresholds = load_context_thresholds(
        max_context_tokens,
        max_output_tokens=max_output_tokens,
    )
    estimated = max(0, int(estimated_tokens or 0))
    auto_enabled = is_auto_compact_enabled()
    tier_base = (
        thresholds.auto_compact_at_tokens
        if auto_enabled
        else thresholds.effective_context_tokens
    )
    percent_left = max(
        0,
        round(((tier_base - estimated) / tier_base) * 100, 1) if tier_base else 0,
    )

    is_above_auto = auto_enabled and estimated >= thresholds.auto_compact_at_tokens
    is_above_warn = estimated >= thresholds.warn_at_tokens
    is_above_error = estimated >= thresholds.error_at_tokens
    is_at_blocking = estimated >= thresholds.blocking_at_tokens

    if is_at_blocking:
        tier, tier_label = "blocking", "阻塞"
    elif is_above_auto:
        tier, tier_label = "critical", "临界"
    elif is_above_warn or is_above_error:
        tier, tier_label = "warn", "预警"
    else:
        tier, tier_label = "ok", "正常"

    pct_of_max = (
        round(100.0 * estimated / thresholds.max_context_tokens, 1)
        if thresholds.max_context_tokens
        else 0.0
    )
    tokens_until_auto = max(0, thresholds.auto_compact_at_tokens - estimated)

    return {
        "context_estimated_tokens": estimated,
        "context_max_tokens": thresholds.max_context_tokens,
        "context_effective_tokens": thresholds.effective_context_tokens,
        "context_usage_percent": pct_of_max,
        "context_percent_left": percent_left,
        "context_tier": tier,
        "context_tier_label": tier_label,
        "context_warn_at_tokens": thresholds.warn_at_tokens,
        "context_error_at_tokens": thresholds.error_at_tokens,
        "context_auto_compact_at_tokens": thresholds.auto_compact_at_tokens,
        "context_blocking_at_tokens": thresholds.blocking_at_tokens,
        "context_tokens_until_auto_compact": tokens_until_auto,
        "context_auto_compact_enabled": auto_enabled,
        "context_is_above_warning": is_above_warn,
        "context_is_above_error": is_above_error,
        "context_is_above_auto_compact": is_above_auto,
        "context_is_at_blocking_limit": is_at_blocking,
        "context_compact_max_failures": thresholds.max_consecutive_compact_failures,
    }


def evaluate_context_budget(
    estimated_tokens: int,
    *,
    max_context_tokens: int,
    max_output_tokens: int | None = None,
) -> dict[str, Any]:
    return calculate_token_warning_state(
        estimated_tokens,
        max_context_tokens=max_context_tokens,
        max_output_tokens=max_output_tokens,
    )


def compact_circuit_open(
    consecutive_failures: int,
    *,
    max_context_tokens: int,
) -> bool:
    thresholds = load_context_thresholds(max_context_tokens)
    return consecutive_failures >= thresholds.max_consecutive_compact_failures


def format_context_budget_line(diagnostics: dict[str, Any]) -> str:
    est = diagnostics.get("context_estimated_tokens")
    eff = diagnostics.get("context_effective_tokens") or diagnostics.get("context_max_tokens")
    tier = diagnostics.get("context_tier_label") or diagnostics.get("context_tier") or "-"
    if est is None or eff is None:
        return "上下文用量: -"

    parts = [
        f"上下文用量: ~{est:,} / {eff:,} 有效 tokens · 档位: {tier}",
    ]
    until = diagnostics.get("context_tokens_until_auto_compact")
    if until is not None and diagnostics.get("context_auto_compact_enabled"):
        parts.append(f"距自动压缩约 {until:,}")
    block_at = diagnostics.get("context_blocking_at_tokens")
    if block_at is not None:
        parts.append(f"阻塞线 {block_at:,}")
    line = " · ".join(parts)
    if diagnostics.get("context_compact_circuit_open"):
        n = diagnostics.get("context_compact_consecutive_failures", 0)
        line += f" · 压缩熔断: 开 (连续失败 {n} 次)"
    elif diagnostics.get("hygiene_compact_noop"):
        line += " · 上次压缩无效果"
    return line
