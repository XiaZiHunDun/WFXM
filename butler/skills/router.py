"""Task-time skill matching for context injection (triggers + TF-IDF)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.skills.similarity import tfidf_cosine

logger = logging.getLogger(__name__)


def _skill_text(skill: dict[str, Any]) -> str:
    desc = str(skill.get("description", "") or "")
    triggers = " ".join(str(t) for t in (skill.get("triggers") or []))
    return f"{desc}\n{triggers}"


class SkillRouter:
    """Match a task string to the most relevant skills (no LLM)."""

    def __init__(
        self,
        skills: list[dict[str, Any]],
        content_loader: Callable[[str], dict[str, Any] | None] | None = None,
        batch_content_loader: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
    ) -> None:
        self._skills = list(skills)
        self._content_loader = content_loader
        self._batch_content_loader = batch_content_loader

    def _payload_for(
        self,
        skill: dict[str, Any],
        score: float,
        loaded_by_name: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "name": skill.get("name"),
            "description": skill.get("description"),
            "triggers": list(skill.get("triggers") or []),
            "content": skill.get("content", skill.get("body", "")),
            "version": skill.get("version"),
            "created": skill.get("created"),
            "match_score": round(score, 4),
        }
        full = None
        if payload["name"] and loaded_by_name:
            full = loaded_by_name.get(str(payload["name"]))
        if self._content_loader and full is None and not payload["content"] and payload["name"]:
            try:
                full = self._content_loader(str(payload["name"]))
            except Exception as exc:
                logger.debug("Skill content load failed for %s: %s", payload["name"], exc)
                full = None
        if isinstance(full, dict):
            payload.update({
                "description": full.get("description", payload.get("description")),
                "triggers": list(full.get("triggers") or payload.get("triggers") or []),
                "content": full.get("content", full.get("body", "")) or "",
                "version": full.get("version", payload.get("version")),
                "created": full.get("created", payload.get("created")),
            })
        return payload

    def match(self, task_description: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Return skill dicts with injection-ready `content` and `match_score`."""
        if not task_description or not self._skills:
            return []

        task_lower = task_description.lower()
        scored: list[tuple[float, dict[str, Any]]] = []

        for skill in self._skills:
            score = 0.0
            for trigger in skill.get("triggers") or []:
                t = str(trigger).strip().lower()
                if t and t in task_lower:
                    score = max(score, 0.9)
                    break

            if score < 0.5:
                st = _skill_text(skill)
                tf = tfidf_cosine(task_description, st)
                score = max(score, tf)

            if score > 0.2:
                scored.append((score, skill))

        scored.sort(key=lambda x: -x[0])
        selected = scored[: max(0, top_k)]
        loaded_by_name: dict[str, dict[str, Any]] = {}
        if self._batch_content_loader:
            names = [
                str(skill.get("name"))
                for _, skill in selected
                if skill.get("name") and not skill.get("content") and not skill.get("body")
            ]
            if names:
                try:
                    loaded = self._batch_content_loader(names)
                    if isinstance(loaded, dict):
                        loaded_by_name = loaded
                except Exception as exc:
                    logger.debug("Batch skill content load failed for %s: %s", names, exc)
        return [
            self._payload_for(skill, score, loaded_by_name=loaded_by_name)
            for score, skill in selected
        ]
