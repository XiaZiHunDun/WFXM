"""H3: owner-facing last-turn memory prefetch / injection transparency."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 60
_SNIPPET_LIMIT = 8


def _merged_health(health: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(health or {})
    loop = base.get("loop")
    if isinstance(loop, dict):
        for key, value in loop.items():
            if key.startswith(("memory_", "skill_")) and key not in base:
                base[key] = value
    return base


def _sanitize_snippet(text: str, *, max_len: int = _SNIPPET_MAX) -> str:
    s = " ".join(str(text or "").split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def build_memory_sources_snapshot(health: dict[str, Any] | None) -> dict[str, Any]:
    """Structured last-turn memory injection facts (stored in session health)."""
    h = _merged_health(health)
    snap: dict[str, Any] = {}

    skipped = h.get("memory_prefetch_skipped")
    if skipped:
        snap["prefetch_skipped"] = str(skipped)

    for key in (
        "memory_experience_hits",
        "memory_project_query_hits",
        "memory_prefetch_chars",
        "memory_prefetch_retrieval_total",
        "memory_prefetch_retrieval_used",
        "skill_injection_mode",
        "skill_injection_reason",
        "skill_injection_experience_hits",
    ):
        if key in h and h[key] is not None:
            snap[key] = h[key]

    flags: list[str] = []
    if h.get("memory_project_context"):
        flags.append("项目记忆上下文")
    if h.get("memory_pim_injected"):
        flags.append("PIM 概览")
    if h.get("memory_prefetch_truncated"):
        flags.append("预取已截断")
    if flags:
        snap["injected_blocks"] = flags

    refs = h.get("skill_injection_refs")
    if isinstance(refs, list) and refs:
        snap["skill_refs"] = [str(r) for r in refs[:6]]

    snippets = h.get("memory_prefetch_snippets")
    if isinstance(snippets, list) and snippets:
        snap["snippet_samples"] = [
            _sanitize_snippet(str(s)) for s in snippets[:_SNIPPET_LIMIT] if str(s).strip()
        ]

    return snap


def snapshot_last_turn_memory_sources(health: dict[str, Any] | None) -> None:
    if health is None:
        return
    snap = build_memory_sources_snapshot(health)
    if snap:
        health["memory_last_turn_sources"] = snap


def _sources_from_health(health: dict[str, Any] | None) -> dict[str, Any]:
    h = dict(health or {})
    stored = h.get("memory_last_turn_sources")
    if isinstance(stored, dict) and stored:
        return stored
    return build_memory_sources_snapshot(h)


def format_memory_sources_one_liner(health: dict[str, Any] | None) -> str:
    snap = _sources_from_health(health)
    if not snap:
        return "记忆来源: 上轮无预取注入"
    if snap.get("prefetch_skipped"):
        return f"记忆来源: 已跳过（{snap['prefetch_skipped']}）"
    parts: list[str] = []
    exp = int(snap.get("memory_experience_hits") or 0)
    if exp:
        parts.append(f"经验{exp}条")
    proj = int(snap.get("memory_project_query_hits") or 0)
    if proj:
        parts.append(f"项目检索{proj}条")
    blocks = snap.get("injected_blocks")
    if isinstance(blocks, list):
        parts.extend(str(b) for b in blocks[:2])
    mode = snap.get("skill_injection_mode")
    reason = snap.get("skill_injection_reason")
    if mode:
        skill_bit = f"Skill:{mode}"
        if reason:
            skill_bit += f"/{reason}"
        parts.append(skill_bit)
    pr_total = int(snap.get("memory_prefetch_retrieval_total") or 0)
    pr_used = int(snap.get("memory_prefetch_retrieval_used") or 0)
    if pr_total:
        parts.append(f"P_r {pr_used}/{pr_total}")
    if not parts:
        chars = int(snap.get("memory_prefetch_chars") or 0)
        if chars:
            return f"记忆来源: 预取 {chars} 字符"
        return "记忆来源: 上轮无预取注入"
    return "记忆来源: " + " · ".join(parts)


def format_memory_sources_report(health: dict[str, Any] | None) -> str:
    snap = _sources_from_health(health)
    lines = ["🧠 上轮记忆来源", ""]
    if not snap:
        lines.append("尚无预取记录。完成一轮对话后再查看。")
        lines.append("")
        lines.append("说明：经验优先、Skill 兜底；回忆清单类问题会跳过预取。")
        return "\n".join(lines)

    if snap.get("prefetch_skipped"):
        lines.append(f"预取: 已跳过（{snap['prefetch_skipped']}）")
    else:
        chars = int(snap.get("memory_prefetch_chars") or 0)
        if chars:
            lines.append(f"预取体积: {chars} 字符")

    exp = int(snap.get("memory_experience_hits") or 0)
    if exp:
        lines.append(f"经验命中: {exp} 条")
    proj = int(snap.get("memory_project_query_hits") or 0)
    if proj:
        lines.append(f"项目语义检索: {proj} 条")
    blocks = snap.get("injected_blocks")
    if isinstance(blocks, list) and blocks:
        lines.append("注入块: " + "、".join(str(b) for b in blocks))

    mode = snap.get("skill_injection_mode")
    if mode:
        reason = snap.get("skill_injection_reason") or ""
        n_exp = snap.get("skill_injection_experience_hits")
        lines.append(f"Skill 策略: {mode}" + (f"（{reason}）" if reason else ""))
        if n_exp is not None:
            lines.append(f"  策略侧经验命中: {n_exp}")
    refs = snap.get("skill_refs")
    if isinstance(refs, list) and refs:
        lines.append("  经验 skill 指针: " + ", ".join(refs))

    pr_total = int(snap.get("memory_prefetch_retrieval_total") or 0)
    if pr_total:
        pr_used = int(snap.get("memory_prefetch_retrieval_used") or 0)
        lines.append(f"P_r 预取引用: {pr_used}/{pr_total} 条在回复中出现")

    samples = snap.get("snippet_samples")
    if isinstance(samples, list) and samples:
        lines.append("")
        lines.append("命中节选（脱敏）:")
        for i, sample in enumerate(samples, 1):
            lines.append(f"  {i}. {sample}")

    lines.append("")
    lines.append("相关: /信任 · /压缩报告 · `BUTLER_SKILL_INJECTION_MODE`")
    return "\n".join(lines)


__all__ = [
    "build_memory_sources_snapshot",
    "format_memory_sources_one_liner",
    "format_memory_sources_report",
    "snapshot_last_turn_memory_sources",
]
