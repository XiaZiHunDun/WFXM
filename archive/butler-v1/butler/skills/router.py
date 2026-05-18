"""Skill router — matches user tasks to relevant skills at runtime.

This runs on the HOT PATH (every task dispatch), so it must be fast:
- Trigger keyword matching (exact substring)
- TF-IDF cosine similarity (lightweight)
- NO LLM calls
"""
from __future__ import annotations

from butler.skills.loader import SkillInfo
from butler.skills.similarity import tfidf_cosine


class SkillRouter:
    """Match user tasks to the most relevant skills."""

    def match(
        self,
        task: str,
        available_skills: list[SkillInfo],
        top_k: int = 2,
    ) -> list[SkillInfo]:
        if not available_skills or not task:
            return []

        task_lower = task.lower()
        scored: list[tuple[float, SkillInfo]] = []

        for skill in available_skills:
            score = 0.0

            # Layer 1: Trigger keyword matching (high weight)
            for trigger in skill.triggers:
                if trigger.lower() in task_lower:
                    score = max(score, 0.9)
                    break

            # Layer 2: TF-IDF similarity on description + body
            if score < 0.5:
                skill_text = f"{skill.description} {' '.join(skill.triggers)}"
                tfidf_score = tfidf_cosine(task, skill_text)
                score = max(score, tfidf_score)

            if score > 0.2:
                scored.append((score, skill))

        scored.sort(key=lambda x: -x[0])
        return [skill for _, skill in scored[:top_k]]
