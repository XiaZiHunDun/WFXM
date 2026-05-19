"""Post-session dual-channel processor for Butler v3.

After a conversation ends, runs two LLM-driven extraction channels:
1. Memory channel: extract user prefs -> ButlerMemory, project facts -> ProjectMemory
2. Skill channel: extract reusable workflows -> SkillManager

Uses Hermes AIAgent for the LLM calls instead of a raw provider.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

LLMCallFn = Callable[[str], Coroutine[Any, Any, str]]

_PROJECT_SECTION_MAP = {
    "架构与设计": "Architecture",
    "架构": "Architecture",
    "设计": "Architecture",
    "关键决策": "Decisions",
    "决策": "Decisions",
    "代码模式与约定": "Patterns",
    "代码模式": "Patterns",
    "约定": "Patterns",
    "API": "API",
    "接口": "API",
    "已知问题": "Notes",
    "问题": "Notes",
    "当前状态": "Notes",
    "状态": "Notes",
}
_PROJECT_CANONICAL_SECTIONS = {"Architecture", "Decisions", "Patterns", "API", "Notes", "Pending"}

_MEMORY_REVIEW_PROMPT = """分析以下对话记录，提取需要长期记住的信息。

## 提取规则
1. 用户偏好/习惯/身份信息 → target: "butler", 存入管家层记忆
2. 项目技术细节（架构/框架/决策/约定/问题）→ target: "project", section 从以下选择:
   - "架构与设计"
   - "关键决策"
   - "代码模式与约定"
   - "已知问题"
   - "当前状态"
3. 跨项目经验教训 → target: "experience"
4. 不要提取：一次性问答、临时调试、已有记忆中重复的内容

## 现有管家记忆
{butler_memory}

## 现有项目记忆
{project_memory}

## 对话记录
{transcript}

输出 JSON:
{{"updates": [
  {{"target": "butler|project|experience", "section": "仅project需要", "content": "内容"}}
]}}
如无需更新返回 {{"updates": []}}"""

_SKILL_EXTRACT_PROMPT = """分析以下对话记录，识别可复用的操作流程。

## 判断标准
1. 必须是可复用的操作策略、分析框架或工作流程
2. 一次性问答或信息查询不算
3. 个人偏好应存入 memory 而非 skill
4. 至少涉及 2 个以上步骤或决策点
5. 已有 skill 不需要重复提炼

## 已有 Skills
{existing_skills}

## 对话记录
{transcript}

输出 JSON:
{{"skills": [
  {{"name": "kebab-case-name", "description": "一句话描述",
    "triggers": ["触发词"], "tools": ["工具名"], "body": "Markdown 工作流",
    "scope": "project|global"}}
]}}
如无发现返回 {{"skills": []}}"""


def _format_messages(messages: list[dict], max_chars: int = 12000) -> str:
    parts: list[str] = []
    total = 0
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        if not content:
            continue
        if role == "TOOL" and len(content) > 500:
            content = content[:200] + f"...[{len(content)} chars]"
        line = f"[{role}]: {content[:800]}"
        if total + len(line) > max_chars:
            break
        parts.append(line)
        total += len(line)
    return "\n\n".join(parts)


def _parse_json_from_response(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _normalize_project_section(section: str) -> str:
    """Map LLM-facing Chinese section names to MEMORY.md's canonical sections."""
    section = str(section or "").strip()
    if section in _PROJECT_CANONICAL_SECTIONS:
        return section
    return _PROJECT_SECTION_MAP.get(section, "Notes")


class PostSessionProcessor:
    """Dual-channel post-session processor.

    Can use either a raw LLM callable or a Hermes AIAgent for extraction.
    """

    def __init__(self, llm_call: LLMCallFn | None = None):
        self._llm_call = llm_call

    def set_llm_call(self, fn: LLMCallFn) -> None:
        self._llm_call = fn

    @classmethod
    def from_hermes_agent(cls, agent: Any) -> "PostSessionProcessor":
        """Create a processor that uses a Hermes AIAgent for LLM calls."""
        async def _llm_call(prompt: str) -> str:
            result = agent.run_conversation(user_message=prompt)
            if isinstance(result, dict):
                return result.get("final_response", "")
            return str(result)

        proc = cls()
        proc.set_llm_call(_llm_call)
        return proc

    async def process(
        self,
        messages: list[dict],
        butler_memory: Any = None,
        project_memory: Any = None,
        skill_manager: Any = None,
        project_name: str = "",
    ) -> dict:
        """Run both memory and skill extraction channels."""
        if not self._llm_call or len(messages) < 4:
            return {"memory_updates": 0, "skills_extracted": 0, "errors": []}

        result = {"memory_updates": 0, "skills_extracted": 0, "errors": []}

        try:
            mem_count = await self._extract_memories(
                messages, butler_memory, project_memory, project_name
            )
            result["memory_updates"] = mem_count
        except Exception as e:
            logger.error("Memory extraction failed: %s", e)
            result["errors"].append(f"Memory: {e}")

        try:
            skill_count = await self._extract_skills(
                messages, skill_manager, project_name
            )
            result["skills_extracted"] = skill_count
        except Exception as e:
            logger.error("Skill extraction failed: %s", e)
            result["errors"].append(f"Skill: {e}")

        return result

    async def _extract_memories(
        self, messages, butler_memory, project_memory, project_name
    ) -> int:
        if not self._llm_call:
            return 0

        transcript = _format_messages(messages)
        if len(transcript) < 200:
            return 0

        butler_ctx = ""
        if butler_memory and hasattr(butler_memory, "get_system_context"):
            butler_ctx = butler_memory.get_system_context()[:1000]

        project_ctx = ""
        if project_memory and hasattr(project_memory, "get_full_context"):
            project_ctx = project_memory.get_full_context(max_lines=20)[:1000]

        prompt = _MEMORY_REVIEW_PROMPT.format(
            butler_memory=butler_ctx or "(空)",
            project_memory=project_ctx or "(空)",
            transcript=transcript,
        )

        raw = await self._llm_call(prompt)
        data = _parse_json_from_response(raw)
        if not data:
            return 0

        updates = data.get("updates", [])
        if not isinstance(updates, list):
            return 0

        applied = 0
        for upd in updates:
            target = upd.get("target", "")
            content = upd.get("content", "")
            section = upd.get("section", "")
            if not content:
                continue

            try:
                if target == "butler" and butler_memory:
                    butler_memory.profile.add(content)
                    applied += 1
                elif target == "project" and project_memory and section:
                    project_memory.markdown.append(_normalize_project_section(section), content)
                    applied += 1
                elif target == "experience" and butler_memory:
                    butler_memory.experience.add(
                        project=project_name, category="experience", content=content,
                    )
                    applied += 1
            except Exception as e:
                logger.warning("Memory update error: %s", e)

        return applied

    async def _extract_skills(self, messages, skill_manager, project_name) -> int:
        if not self._llm_call or not skill_manager:
            return 0

        transcript = _format_messages(messages)
        if len(transcript) < 300:
            return 0

        existing = ""
        if hasattr(skill_manager, "list_skills"):
            names = [s.get("name", "") for s in skill_manager.list_skills()]
            existing = ", ".join(names) if names else "(none)"
        elif hasattr(skill_manager, "skill_names"):
            existing = ", ".join(skill_manager.skill_names())

        prompt = _SKILL_EXTRACT_PROMPT.format(
            existing_skills=existing or "(none)",
            transcript=transcript,
        )

        raw = await self._llm_call(prompt)
        data = _parse_json_from_response(raw)
        if not data:
            return 0

        skills = data.get("skills", [])
        if not isinstance(skills, list):
            return 0

        created = 0
        for s in skills[:2]:
            if not isinstance(s, dict) or not s.get("name") or not s.get("body"):
                continue
            try:
                skill_data = {
                    "name": str(s["name"]),
                    "description": str(s.get("description", "")),
                    "content": str(s["body"]),
                    "triggers": s.get("triggers", []),
                }
                skill_manager.create(
                    name=skill_data["name"],
                    description=skill_data["description"],
                    triggers=skill_data.get("triggers", []),
                    content=skill_data["content"],
                )
                created += 1
                logger.info("Extracted skill: %s", s["name"])
            except Exception as e:
                logger.warning("Skill creation error: %s", e)

        return created
