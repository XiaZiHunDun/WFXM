"""Wire trusted fusion LLM into SkillManager similarity + consolidator."""

from __future__ import annotations

import logging

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def skill_fusion_enabled() -> bool:
    return env_truthy("BUTLER_SKILL_FUSION", default=True)


def wire_skill_manager_fusion(manager) -> None:
    """Attach fusion LLM to ``SkillManager`` when enabled."""
    if not skill_fusion_enabled():
        return
    try:
        from butler.transport.fusion_client import make_fusion_llm_fn

        manager.set_llm_fn(make_fusion_llm_fn())
    except Exception as exc:
        logger.warning("Skill fusion wiring skipped: %s", exc)


__all__ = ["skill_fusion_enabled", "wire_skill_manager_fusion"]
