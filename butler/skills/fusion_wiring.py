"""Wire trusted fusion LLM into SkillManager similarity + consolidator."""

from __future__ import annotations

from typing import Any

from butler.env_parse import env_truthy


def skill_fusion_enabled() -> bool:
    return bool(env_truthy("BUTLER_SKILL_FUSION", default=True))


def wire_skill_manager_fusion(manager: Any) -> None:
    """Attach fusion LLM to ``SkillManager`` when enabled."""
    if not skill_fusion_enabled():
        return
    from butler.skills.fusion_wiring_ops import wire_fusion_llm_fn_safe

    wire_fusion_llm_fn_safe(manager)


__all__ = ["skill_fusion_enabled", "wire_skill_manager_fusion"]
