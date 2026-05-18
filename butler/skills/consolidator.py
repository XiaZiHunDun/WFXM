"""Skill consolidator — merge multiple similar skills into one via LLM."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

LLMCallFn = Callable[[str], Coroutine[Any, Any, str]]

_MERGE_PROMPT = """你是一个 Skill 合并专家。以下是 {count} 个被判定为高度相似的 Skill，请将它们合并为 1 个更完整的 Skill。

## 合并规则
1. triggers: 取所有 skill 的 triggers 并集，去重
2. tools: 取所有 skill 的 tools 并集，去重
3. description: 写一个更概括的描述
4. name: kebab-case，能覆盖所有原 skill 含义
5. body: 合并所有工作流程步骤，保留独特流程，消除重复

## 原始 Skills
{skills_content}

输出 JSON:
{{"name": "merged-name", "description": "...", "triggers": [...], "tools": [...], "body": "..."}}"""


@dataclass
class MergeResult:
    success: bool
    merged_skill: Optional[dict[str, Any]] = None
    old_names: list[str] = field(default_factory=list)
    error: str = ""


class SkillConsolidator:
    def __init__(self, llm_call: Optional[LLMCallFn] = None):
        self._llm_call = llm_call

    def set_llm_call(self, fn: LLMCallFn) -> None:
        self._llm_call = fn

    async def merge(self, skills: list[dict]) -> MergeResult:
        if not skills:
            return MergeResult(success=False, error="No skills to merge")
        if len(skills) == 1:
            return MergeResult(success=True, merged_skill=skills[0], old_names=[skills[0].get("name", "")])
        if not self._llm_call:
            return MergeResult(success=False, error="LLM call not configured")
        old_names = [s.get("name", "") for s in skills]
        parts = []
        for i, skill in enumerate(skills, 1):
            part = f"### Skill {i}: {skill.get('name', '?')}\n"
            part += f"描述: {skill.get('description', '')}\n"
            part += f"触发词: {', '.join(skill.get('triggers', []))}\n"
            body = skill.get("body", "")[:3000]
            part += f"内容:\n{body}\n"
            parts.append(part)
        prompt = _MERGE_PROMPT.format(count=len(skills), skills_content="\n---\n".join(parts))
        try:
            response = await self._llm_call(prompt)
            json_match = re.search(r'\{.*\}', response.strip(), re.DOTALL)
            if not json_match:
                return MergeResult(success=False, old_names=old_names, error="No valid JSON from LLM")
            data = json.loads(json_match.group())
            merged = {
                "name": str(data.get("name", "")),
                "description": str(data.get("description", ""))[:1024],
                "triggers": [str(t) for t in data.get("triggers", [])] if isinstance(data.get("triggers"), list) else [],
                "tools": [str(t) for t in data.get("tools", [])] if isinstance(data.get("tools"), list) else [],
                "body": str(data.get("body", "")),
            }
            return MergeResult(success=True, merged_skill=merged, old_names=old_names)
        except Exception as e:
            return MergeResult(success=False, old_names=old_names, error=str(e))
