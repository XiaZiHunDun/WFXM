"""Task-time skill matching for context injection (triggers + semantic + TF-IDF)."""

from __future__ import annotations

import threading
from typing import Any, Callable, cast

from butler.skills.similarity import tfidf_cosine

_EMBEDDING_CACHE_MAX = 1024
_embedding_cache: dict[str, list[float]] = {}
_embedding_cache_lock = threading.Lock()


def _get_embedder_safe() -> Any:
    """Get embedder if available, None otherwise (avoids import cost when disabled)."""
    from butler.skills.router_ops import get_skill_embedder_safe

    return get_skill_embedder_safe()


def _skill_text(skill: dict[str, Any]) -> str:
    desc = str(skill.get("description", "") or "")
    triggers = " ".join(str(t) for t in (skill.get("triggers") or []))
    return f"{desc}\n{triggers}"


def _embed_skill(embedder: Any, skill: dict[str, Any]) -> list[float]:
    """Embed skill text with caching by skill name + description hash."""
    from butler.skills.router_ops import embed_text_safe

    text = _skill_text(skill)
    cache_key = f"skill:{skill.get('name', '')}:{hash(text)}"
    with _embedding_cache_lock:
        if cache_key in _embedding_cache:
            _embedding_cache[cache_key] = _embedding_cache.pop(cache_key)
            return _embedding_cache[cache_key]
    vec = embed_text_safe(embedder, text)
    if not vec:
        return []
    with _embedding_cache_lock:
        if len(_embedding_cache) >= _EMBEDDING_CACHE_MAX:
            oldest = next(iter(_embedding_cache))
            _embedding_cache.pop(oldest, None)
        _embedding_cache[cache_key] = vec
    return cast(list[float], vec)


class SkillRouter:
    """Match a task string to the most relevant skills (triggers + semantic + TF-IDF)."""

    def __init__(
        self,
        skills: list[dict[str, Any]],
        content_loader: Callable[[str], dict[str, Any] | None] | None = None,
        batch_content_loader: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
    ) -> None:
        self._skills = [
            sk for sk in list(skills)
            if str(sk.get("_load_policy") or "inject") != "block"
        ]
        self._content_loader = content_loader
        self._batch_content_loader = batch_content_loader
        self._embedder = _get_embedder_safe()

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
            "preferred_tools": list(skill.get("preferred_tools") or []),
        }
        full = None
        if payload["name"] and loaded_by_name:
            full = loaded_by_name.get(str(payload["name"]))
        if self._content_loader and full is None and not payload["content"] and payload["name"]:
            from butler.skills.router_ops import load_skill_content_safe

            full = load_skill_content_safe(self._content_loader, str(payload["name"]))
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
        """Return skill dicts with injection-ready `content` and `match_score`.

        Scoring cascade:
        1. Trigger substring match → 0.9
        2. Semantic embedding similarity (if embedder available) → cosine score * 0.85
        3. TF-IDF cosine fallback → raw cosine score
        """
        if not task_description or not self._skills:
            return []

        task_lower = task_description.lower()
        scored: list[tuple[float, dict[str, Any]]] = []

        query_vec: list[float] = []
        if self._embedder:
            from butler.skills.router_ops import embed_text_safe

            query_vec = embed_text_safe(self._embedder, task_description)

        for skill in self._skills:
            score = 0.0
            for trigger in skill.get("triggers") or []:
                t = str(trigger).strip().lower()
                if t and t in task_lower:
                    score = max(score, 0.9)
                    break

            if score < 0.5 and query_vec and self._embedder:
                skill_vec = _embed_skill(self._embedder, skill)
                if skill_vec:
                    from butler.memory.embedding import cosine_similarity

                    sim = cosine_similarity(query_vec, skill_vec)
                    score = max(score, sim * 0.85)

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
                from butler.skills.router_ops import batch_load_skill_content_safe

                loaded_by_name = batch_load_skill_content_safe(self._batch_content_loader, names)
        return [
            self._payload_for(skill, score, loaded_by_name=loaded_by_name)
            for score, skill in selected
        ]

    def get_preferred_tools(self, task_description: str, top_k: int = 3) -> set[str]:
        """Return the union of preferred_tools from matched skills."""
        matched = self.match(task_description, top_k=top_k)
        tools: set[str] = set()
        for skill in matched:
            pt = skill.get("preferred_tools") or []
            if isinstance(pt, list):
                tools.update(str(t) for t in pt if t)
        return tools

    def get_preferred_tools_for_names(self, names: list[str]) -> set[str]:
        """Return preferred_tools for explicitly named skills (experience ``skill:`` refs)."""
        wanted = {str(n).strip().lower() for n in names if str(n).strip()}
        if not wanted:
            return set()
        tools: set[str] = set()
        for skill in self._skills:
            name = str(skill.get("name") or "").strip().lower()
            if name not in wanted:
                continue
            pt = skill.get("preferred_tools") or []
            if isinstance(pt, list):
                tools.update(str(t) for t in pt if t)
        return tools
