"""Compaction outcome labels for /诊断 (Gemini CompressionStatus subset)."""

from __future__ import annotations

from typing import Any


def derive_compaction_status(health: dict[str, Any] | None) -> str:
    """Return human-readable compaction state from turn diagnostics."""
    h = health or {}
    if h.get("hygiene_compressed") or h.get("context_compressed"):
        return "compressed"
    if h.get("preemptive_truncate_applied") or h.get("hygiene_truncate_only"):
        return "truncated_only"
    if h.get("hygiene_compact_failed") or h.get("hygiene_compact_error"):
        return "compress_failed"
    if h.get("hygiene_compact_noop") and (
        h.get("hygiene_estimated_tokens", 0) > h.get("hygiene_threshold_tokens", 0)
    ):
        return "inflated_fail"
    if h.get("context_compact_circuit_open"):
        return "circuit_open"
    if h.get("hygiene_compact_skipped"):
        return f"skipped:{h.get('hygiene_compact_skipped')}"
    if h.get("preemptive_compact_applied"):
        return "preemptive_compact"
    return "none"


def format_compaction_status_line(health: dict[str, Any] | None) -> str:
    status = derive_compaction_status(health)
    labels = {
        "compressed": "已压缩",
        "truncated_only": "仅截断工具输出（未摘要）",
        "inflated_fail": "压缩无效（摘要后仍超限）",
        "compress_failed": "压缩失败",
        "circuit_open": "压缩熔断",
        "preemptive_compact": "预检压缩",
        "none": "否",
    }
    text = labels.get(status, status)
    extra = ""
    if health and health.get("hygiene_estimated_tokens_after"):
        extra = (
            f" (~{health.get('hygiene_estimated_tokens', '?')}→"
            f"{health.get('hygiene_estimated_tokens_after', '?')} tokens)"
        )
    return f"压缩状态: {text}{extra}"


__all__ = ["derive_compaction_status", "format_compaction_status_line"]
