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


def format_compaction_detail_line(health: dict[str, Any] | None) -> str:
    h = health or {}
    phase = str(h.get("compaction_phase") or "").strip()
    reason = str(h.get("compaction_reason") or "").strip()
    if not phase and not reason:
        return ""
    parts = []
    if phase:
        parts.append(f"phase={phase}")
    if reason:
        parts.append(f"reason={reason}")
    inj = str(h.get("compaction_initial_injection") or "").strip()
    if inj:
        parts.append(f"injection={inj}")
    return "压缩相位: " + ", ".join(parts)


def format_compaction_status_line(health: dict[str, Any] | None) -> str:
    status = derive_compaction_status(health)
    detail = format_compaction_detail_line(health)
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
    line = f"压缩状态: {text}{extra}"
    if detail:
        line += f"；{detail}"
    hook_ctx = str((health or {}).get("compaction_hook_context") or "").strip()
    if hook_ctx:
        line += f"；hook上下文={len(hook_ctx)}字"
    acl_deg = (health or {}).get("compaction_acl_degraded")
    if acl_deg:
        line += "；ACL降级"
    return line


def format_fact_survival_line(health: dict[str, Any] | None) -> str:
    """Turn-level and session-level S_f for /诊断."""
    h = health or {}
    store = h.get("facts_store_count")
    anchor = h.get("facts_anchor_count")
    if store is not None and anchor is not None and int(store) > 0:
        rate = h.get("fact_survival_rate_turn")
        if rate is None:
            rate = round(int(anchor) / int(store), 4)
        return f"事实锚点: {store}条存储→{anchor}条入锚 (S_f≈{float(rate):.0%})"

    mm = h.get("memory_metrics") if isinstance(h.get("memory_metrics"), dict) else {}
    anchor_sf = mm.get("anchor_fact_survival_rate")
    if anchor_sf is not None and h.get("anchor_facts_pre", 0):
        pre = h.get("anchor_facts_pre")
        post = h.get("anchor_facts_post")
        return f"记忆度量 S_f(锚点): {post}/{pre} ({float(anchor_sf):.0%})"

    extract_sf = mm.get("fact_survival_rate")
    if extract_sf is not None and h.get("facts_pre_compact", 0):
        pre = h.get("facts_pre_compact")
        post = h.get("facts_post_compact")
        return f"记忆度量 S_f(提取): {post}/{pre} ({float(extract_sf):.0%})"

    return ""


def promote_compaction_diagnostics_to_health(health: dict[str, Any], loop_diag: dict[str, Any]) -> None:
    """Copy compaction / fact fields from loop diagnostics into top-level health."""
    prefixes = ("compaction_", "post_compact_", "facts_", "hygiene_", "context_", "preemptive_")
    for key, value in loop_diag.items():
        if key.startswith(prefixes) or key in {
            "hygiene_compressed",
            "context_compressed",
            "reactive_context_compact",
        }:
            health[key] = value


def format_compaction_report(
    session_key: str,
    health: dict[str, Any] | None = None,
) -> str:
    """WeChat-facing compaction summary (checkpoint + transcript + turn health)."""
    sk = str(session_key or "").strip()
    h = health or {}
    lines = ["## 压缩报告", format_compaction_status_line(h)]
    fact_line = format_fact_survival_line(h)
    if fact_line:
        lines.append(fact_line)
    acl_version = str(h.get("compaction_view_version") or "").strip()
    if acl_version:
        lines.append(f"ACL 契约: {acl_version}")
    acl_shape = str(h.get("compaction_acl_shape") or "").strip()
    if acl_shape:
        lines.append(f"ACL 形态: {acl_shape}")
    hook_ctx = str(h.get("compaction_hook_context") or "").strip()
    if hook_ctx:
        lines.append(f"Hook 上下文: {len(hook_ctx)}字")

    ckpt: dict[str, Any] | None = None
    if sk:
        from butler.core.compaction_status_ops import load_checkpoint_safe

        ckpt = load_checkpoint_safe(sk)
    if ckpt:
        captured = str(ckpt.get("captured_at") or "").strip()
        if captured:
            lines.append(f"检查点: {captured}")
        preview = str(ckpt.get("compression_summary_preview") or "").strip()
        if preview:
            lines.append(f"摘要节选 ({len(preview)}字):\n{preview}")

    if sk:
        from butler.core.compaction_status_ops import last_compact_transcript_line

        line = last_compact_transcript_line(sk)
        if line:
            lines.append(line)

    if len(lines) <= 2 and derive_compaction_status(h) == "none" and not ckpt:
        lines.append("本会话尚无压缩记录。")
    return "\n".join(lines)


__all__ = [
    "derive_compaction_status",
    "format_compaction_detail_line",
    "format_compaction_report",
    "format_compaction_status_line",
    "format_fact_survival_line",
    "promote_compaction_diagnostics_to_health",
]
