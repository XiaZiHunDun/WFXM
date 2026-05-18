"""LLM-driven merge of multiple similar skills into one."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

LLMFn = Callable[[str], str]

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
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
    return None


class SkillConsolidator:
    def __init__(self, llm_fn: Optional[LLMFn] = None) -> None:
        self._llm_fn = llm_fn

    def set_llm_fn(self, fn: Optional[LLMFn]) -> None:
        self._llm_fn = fn

    def consolidate(self, skills: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge skills into one dict. Passthrough if len<=1 or no LLM."""
        if not skills:
            raise ValueError("consolidate requires at least one skill")
        if len(skills) == 1:
            return dict(skills[0])
        if self._llm_fn is None:
            return _fallback_merge(skills)

        blocks: list[str] = []
        for i, s in enumerate(skills, 1):
            body = str(s.get("content", s.get("body", "")))
            if len(body) > 4000:
                body = body[:4000] + "\n..."
            part = (
                f"### Skill {i}: {s.get('name', '')}\n"
                f"description: {s.get('description', '')}\n"
                f"triggers: {s.get('triggers', [])}\n"
                f"content:\n{body}\n"
            )
            blocks.append(part)
        prompt = _MERGE_PROMPT.format(blocks="\n---\n".join(blocks))
        try:
            raw = self._llm_fn(prompt)
            data = _extract_json_object(raw)
            if not data:
                logger.warning("Consolidator: no JSON from LLM, using fallback merge")
                return _fallback_merge(skills)
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
            out = {
                "name": name,
                "description": desc,
                "triggers": triggers,
                "content": content,
                "version": int(skills[0].get("version", 1) or 1),
                "created": str(skills[0].get("created", date.today().isoformat())),
            }
            return out
        except Exception as e:
            logger.warning("Consolidator LLM error: %s — using fallback merge", e)
            return _fallback_merge(skills)


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
