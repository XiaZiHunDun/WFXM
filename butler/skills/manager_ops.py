"""Best-effort helpers for SkillManager (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from butler.core.best_effort import safe_best_effort


def enrich_skill_load_policy_safe(
    sk: dict[str, Any],
    path: Path,
    source: str,
    *,
    record_block: Callable[[str], None],
) -> dict[str, Any] | None:
    def _run() -> dict[str, Any] | None:
        from butler.skills.guard import (
            evaluate_skill_load_policy,
            skill_requires_trust_disclaimer,
        )

        policy = evaluate_skill_load_policy(path, source=source)
        if policy == "block":
            record_block(f"Skill blocked by guard trust policy: {path.name}")
            return None
        out = dict(sk)
        out["_load_policy"] = policy
        if skill_requires_trust_disclaimer(policy):
            out["_trust_warn"] = True
        return out

    result = safe_best_effort(
        _run,
        label="skills.manager.load_policy",
        default=sk,
    )
    if result is sk:
        return cast(dict[str, Any] | None, sk)
    return result if isinstance(result, dict) else sk


def maybe_queue_skill_pending_safe(
    *,
    name: str,
    description: str,
    triggers: list[str],
    content: str,
) -> str | None:
    def _run() -> str | None:
        from butler.skills.write_approval import (
            queue_skill_pending,
            skill_write_approval_enabled,
        )

        if not skill_write_approval_enabled():
            return None
        queue_skill_pending(
            name=name,
            description=description,
            triggers=triggers,
            content=content,
        )
        return "pending"

    result = safe_best_effort(_run, label="skills.manager.write_approval", default=None)
    return result if result == "pending" else None


def record_skill_merge_fallback_safe() -> None:
    def _run() -> None:
        from butler.ops.degradation_registry import register_degradation
        from butler.ops.runtime_metrics import inc

        register_degradation(
            "skills",
            "合并使用确定性 fallback（LLM 不可用或无 JSON）",
        )
        inc("digestion_skill_fallback_merge")

    safe_best_effort(_run, label="skills.manager.merge_fallback", default=None)
