"""Registry-specific exceptions."""

from __future__ import annotations

from butler.registry.skill_types import SkillSearchHit


class InstallConfirmationRequired(Exception):
    """Community (or similar) skill install needs explicit Owner confirmation."""

    def __init__(self, hit: SkillSearchHit) -> None:
        self.hit = hit
        super().__init__(f"confirmation required for {hit.identifier}")
