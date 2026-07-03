"""Skill injection trust policy: experience-first, skill fallback (tiered retrieval)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

_SKILL_REF_RE = re.compile(
    r"skill:([a-z0-9][a-z0-9._-]*)",
    re.IGNORECASE,
)

_VALID_MODES = frozenset({"always", "fallback", "ref_only"})


def skill_injection_mode() -> str:
    raw = os.getenv("BUTLER_SKILL_INJECTION_MODE", "fallback").strip().lower()
    return raw if raw in _VALID_MODES else "fallback"


def skill_fallback_min_experience_hits() -> int:
    try:
        from butler.env_parse import int_env

        return int_env("BUTLER_SKILL_FALLBACK_MIN_EXPERIENCE_HITS", 1, min=0)
    except ValueError:
        return 1


def extract_skill_refs_from_hits(hits: list[dict[str, Any]]) -> list[str]:
    """Parse ``skill:<name>`` from experience tags and content."""
    seen: set[str] = set()
    ordered: list[str] = []
    for hit in hits:
        tags = hit.get("tags") or ""
        if isinstance(tags, list):
            blob = " ".join(str(t) for t in tags)
        else:
            blob = str(tags)
        blob = f"{blob} {hit.get('content', '')}"
        for m in _SKILL_REF_RE.finditer(blob):
            name = m.group(1).strip().lower()
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
    return ordered


@dataclass(frozen=True)
class SkillInjectionDecision:
    mode: str
    skip: bool
    skill_names: tuple[str, ...]
    experience_hits: int
    reason: str


def resolve_skill_injection(
    orchestrator: Any,
    query: str,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> SkillInjectionDecision:
    """Decide whether to inject skill bodies and which skills to load."""
    from butler.session.memory_prefetch import peek_experience_hits

    mode = skill_injection_mode()
    from butler.skills.injection_policy_ops import (
        is_session_read_recall_intent_safe,
        record_skill_injection_metrics_safe,
    )

    recall_intent = is_session_read_recall_intent_safe(query)
    if recall_intent is True:
        decision = SkillInjectionDecision(
            mode=mode,
            skip=True,
            skill_names=(),
            experience_hits=0,
            reason="session_read_recall",
        )
        if diagnostics is not None:
            diagnostics["skill_injection_mode"] = mode
            diagnostics["skill_injection_experience_hits"] = 0
        record_skill_injection_metrics_safe(decision)
        return decision

    hits = peek_experience_hits(orchestrator, query)
    n_exp = len(hits)
    refs = extract_skill_refs_from_hits(hits)
    min_hits = skill_fallback_min_experience_hits()

    if diagnostics is not None:
        diagnostics["skill_injection_mode"] = mode
        diagnostics["skill_injection_experience_hits"] = n_exp
        if refs:
            diagnostics["skill_injection_refs"] = list(refs)

    if mode == "always":
        decision = SkillInjectionDecision(
            mode=mode,
            skip=False,
            skill_names=(),
            experience_hits=n_exp,
            reason="always",
        )
        record_skill_injection_metrics_safe(decision)
        return decision

    if mode == "ref_only":
        if refs:
            decision = SkillInjectionDecision(
                mode=mode,
                skip=False,
                skill_names=tuple(refs),
                experience_hits=n_exp,
                reason="experience_skill_ref",
            )
            record_skill_injection_metrics_safe(decision)
            return decision
        if n_exp >= min_hits:
            decision = SkillInjectionDecision(
                mode=mode,
                skip=True,
                skill_names=(),
                experience_hits=n_exp,
                reason="experience_hit_no_skill_ref",
            )
            record_skill_injection_metrics_safe(decision)
            return decision
        decision = SkillInjectionDecision(
            mode=mode,
            skip=False,
            skill_names=(),
            experience_hits=n_exp,
            reason="router_fallback_no_ref",
        )
        record_skill_injection_metrics_safe(decision)
        return decision

    # fallback (default): skip router when experience hits suffice
    if n_exp >= min_hits:
        if refs:
            decision = SkillInjectionDecision(
                mode=mode,
                skip=False,
                skill_names=tuple(refs),
                experience_hits=n_exp,
                reason="experience_hit_with_ref",
            )
            record_skill_injection_metrics_safe(decision)
            return decision
        decision = SkillInjectionDecision(
            mode=mode,
            skip=True,
            skill_names=(),
            experience_hits=n_exp,
            reason="experience_hit_skip_unverified_skill",
        )
        record_skill_injection_metrics_safe(decision)
        return decision
    decision = SkillInjectionDecision(
        mode=mode,
        skip=False,
        skill_names=(),
        experience_hits=n_exp,
        reason="router_fallback_no_experience",
    )
    record_skill_injection_metrics_safe(decision)
    return decision


def skill_summary_disclaimer() -> str:
    mode = skill_injection_mode()
    if mode == "always":
        return ""
    return (
        "> 未验证技能目录（第三方/生态 Skill）。"
        "检索时 **经验与项目记忆优先**；仅当经验未覆盖或经验含 `skill:<名>` 指针时才注入正文。"
    )
