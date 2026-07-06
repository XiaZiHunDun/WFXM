"""LLM-driven merge of multiple similar skills into one."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Callable, Optional, cast

logger = logging.getLogger(__name__)

LLMFn = Callable[[str], str]


class ConsolidatorLLMUnavailable(RuntimeError):
    """Raised by _llm_fn when the LLM provider is not reachable.

    The consolidator catches this specific class and falls back to a
    deterministic merge (with fallback_used=True). All other exceptions
    from _llm_fn propagate so callers can decide.
    """

_MERGE_PROMPT = """You are a skill consolidator. Merge the following skills into ONE skill.
Rules:
- name: kebab-case, filesystem-safe (lowercase letters, digits, dots, hyphens, underscores)
- description: concise, max 1024 chars
- triggers: union of all triggers, deduplicated, as a JSON array of strings
- content: merged markdown body with clear steps; remove duplication; keep distinct procedures

Input skills:
{blocks}

Output ONLY valid JSON:
{{"name": "...", "description": "...", "triggers": ["..."], "content": "..."}}
"""


def _extract_json_object(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()
    for pattern in (r"\{[^{}]*\}", r"\{.*\}"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return cast(dict[str, Any], json.loads(m.group()))
            except json.JSONDecodeError:
                continue
    return None


class SkillConsolidator:
    def __init__(self, llm_fn: Optional[LLMFn] = None) -> None:
        self._llm_fn = llm_fn

    def set_llm_fn(self, fn: Optional[LLMFn]) -> None:
        self._llm_fn = fn

    def consolidate(self, skills: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge skills into one dict. Sets fallback_used flag on every path.

        fallback_used is True when the result came from the deterministic
        fallback (no LLM, garbled JSON, or ConsolidatorLLMUnavailable).
        Callers can inspect this flag to detect silent fallbacks and decide
        whether to accept the result, retry, or surface an error.
        """
        if not skills:
            raise ValueError("consolidate requires at least one skill")
        if len(skills) == 1:
            return dict(skills[0])
        if self._llm_fn is None:
            return _with_fallback_flag(_fallback_merge(skills))

        prompt = _build_merge_prompt(skills)
        try:
            raw = self._llm_fn(prompt)
        except ConsolidatorLLMUnavailable as e:
            # Audit R2-1: only the "LLM provider down" case is a true fallback.
            # Other exceptions (data corruption, programming errors) propagate.
            logger.warning("Consolidator LLM unavailable: %s — using fallback merge", e)
            return _with_fallback_flag(_fallback_merge(skills))

        data = _extract_json_object(raw)
        if not data:
            logger.warning("Consolidator: no JSON from LLM, using fallback merge")
            return _with_fallback_flag(_fallback_merge(skills))

        return _build_merged_skill(data, skills)


def _build_merge_prompt(skills: list[dict[str, Any]]) -> str:
    """Render the LLM prompt for merging the given skills."""
    blocks: list[str] = []
    for i, s in enumerate(skills, 1):
        body = str(s.get("content", s.get("body", "")))
        if len(body) > 4000:
            body = body[:4000] + "\n..."
        blocks.append(
            f"### Skill {i}: {s.get('name', '')}\n"
            f"description: {s.get('description', '')}\n"
            f"triggers: {s.get('triggers', [])}\n"
            f"content:\n{body}\n"
        )
    return _MERGE_PROMPT.format(blocks="\n---\n".join(blocks))


def _build_merged_skill(
    data: dict[str, Any],
    skills: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the final merge dict from LLM-extracted JSON data."""
    name = str(data.get("name", skills[0].get("name", "merged-skill"))).strip()
    desc = str(data.get("description", ""))[:1024]
    triggers_raw = data.get("triggers", [])
    if isinstance(triggers_raw, str):
        triggers = [triggers_raw]
    elif isinstance(triggers_raw, list):
        triggers = [str(t) for t in triggers_raw]
    else:
        triggers = []
    content = str(data.get("content", ""))
    return {
        "name": name,
        "description": desc,
        "triggers": triggers,
        "content": content,
        "version": int(skills[0].get("version", 1) or 1),
        "created": str(skills[0].get("created", date.today().isoformat())),
        "fallback_used": False,
    }


def _with_fallback_flag(merge: dict[str, Any]) -> dict[str, Any]:
    """Tag a fallback merge result so callers can detect silent fallbacks."""
    merge["fallback_used"] = True
    return merge


def _fallback_merge(skills: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic merge when LLM is unavailable."""
    names = [str(s.get("name", "")) for s in skills if s.get("name")]
    base = names[0] if names else "merged-skill"
    name = base if len(skills) == 1 else f"{base}-merged"

    triggers_set: set[str] = set()
    for s in skills:
        for t in s.get("triggers") or []:
            triggers_set.add(str(t).strip())
    descs = [str(s.get("description", "")).strip() for s in skills if s.get("description")]
    description = descs[0] if descs else "Merged skill."
    if len(descs) > 1:
        description = description[:900] + " (merged)"

    parts: list[str] = []
    for s in skills:
        parts.append(f"## {s.get('name', 'skill')}\n\n{str(s.get('content', s.get('body', '')))}")
    content = "\n\n---\n\n".join(parts)

    return {
        "name": name,
        "description": description[:1024],
        "triggers": sorted(triggers_set),
        "content": content,
        "version": int(skills[0].get("version", 1) or 1),
        "created": str(skills[0].get("created", date.today().isoformat())),
    }
