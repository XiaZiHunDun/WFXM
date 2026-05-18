"""Task-time skill matching for context injection (triggers + TF-IDF)."""

from __future__ import annotations

from typing import Any

from butler.skills.similarity import tfidf_cosine


def _skill_text(skill: dict[str, Any]) -> str:
    desc = str(skill.get("description", "") or "")
    triggers = " ".join(str(t) for t in (skill.get("triggers") or []))
    return f"{desc}\n{triggers}"


class SkillRouter:
    """Match a task string to the most relevant skills (no LLM)."""

    def __init__(self, skills: list[dict[str, Any]]) -> None:
        self._skills = list(skills)

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
                payload = {
                    "name": skill.get("name"),
                    "description": skill.get("description"),
                    "triggers": list(skill.get("triggers") or []),
                    "content": skill.get("content", skill.get("body", "")),
                    "version": skill.get("version"),
                    "created": skill.get("created"),
                    "match_score": round(score, 4),
                }
                scored.append((score, payload))

        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored[: max(0, top_k)]]
