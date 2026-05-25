"""SkillSource adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from butler.registry.skill_types import SkillBundle, SkillSearchHit


class SkillSource(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str:
        ...

    @abstractmethod
    def search(self, query: str, *, limit: int = 20) -> list[SkillSearchHit]:
        ...

    @abstractmethod
    def inspect(self, identifier: str) -> SkillSearchHit | None:
        ...

    @abstractmethod
    def fetch(self, identifier: str) -> SkillBundle | None:
        ...
