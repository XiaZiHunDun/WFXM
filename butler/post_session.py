"""Post-session dual-channel processor for Butler v3.

After a conversation ends, runs two LLM-driven extraction channels:
1. Memory channel: extract user prefs -> ButlerMemory, project facts -> ProjectMemory
2. Skill channel: extract reusable workflows -> SkillManager

Uses an injected LLM callable (default: ``auxiliary_client`` / Butler transport).
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from typing import Any, Callable, Coroutine, Union

logger = logging.getLogger(__name__)

LLMCallFn = Callable[[str], Union[str, Coroutine[Any, Any, str]]]

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
5. 不要把 novel-factory/workflow_state.json 整份写入记忆；至多一条「当前状态」摘要写入 project section「当前状态」/Notes
6. 用户称呼/微信风格 → butler(profile)；项目决策 → project；勿把「默认项目名」写入 profile（由环境变量 BUTLER_DEFAULT_PROJECT 决定）
7. 含「决定/采用/迁移」等决策语气 → project，系统会自动进入 Pending 待用户 /批准记忆
8. 若与下方「现有管家记忆」「现有项目记忆」已实质相同（同义复述），不要输出该条 update

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


_TS_BULLET_RE = re.compile(r"\[[\d\-:\s]+\]\s*")


def _normalize_for_dedup(text: str) -> str:
    t = _TS_BULLET_RE.sub("", str(text or ""))
    t = re.sub(r"\s+", " ", t.strip().lower())
    return t


def _build_existing_memory_corpus(butler_memory: Any, project_memory: Any) -> str:
    parts: list[str] = []
    if butler_memory is not None:
        if hasattr(butler_memory, "profile"):
            try:
                parts.append(str(butler_memory.profile.read() or ""))
            except Exception:
                pass
        exp = getattr(butler_memory, "experience", None)
        if exp is not None and hasattr(exp, "get_recent"):
            try:
                from butler.session_lifecycle import filter_non_conversation_experience

                for row in filter_non_conversation_experience(exp.get_recent(limit=40)):
                    parts.append(str(row.get("content") or ""))
            except Exception:
                pass
    if project_memory is not None and hasattr(project_memory, "get_full_context"):
        try:
            parts.append(str(project_memory.get_full_context(max_lines=80) or ""))
        except Exception:
            pass
    return "\n".join(p for p in parts if isinstance(p, str) and p.strip())


def memory_update_is_duplicate(content: str, corpus: str, *, min_len: int = 14) -> bool:
    """True when normalized content is already present in the memory corpus."""
    norm = _normalize_for_dedup(content)
    if len(norm) < min_len:
        return False
    corpus_norm = _normalize_for_dedup(corpus)
    if not corpus_norm:
        return False
    if norm in corpus_norm:
        return True
    # Near-duplicate: same text after stripping common pilot prefixes
    for prefix in ("试点进度：", "试点验收", "请记住：", "请记住:"):
        if norm.startswith(_normalize_for_dedup(prefix)):
            stripped = norm[len(_normalize_for_dedup(prefix)) :].strip()
            if stripped and stripped in corpus_norm:
                return True
    return False


class PostSessionProcessor:
    """Dual-channel post-session processor.

    Can use either a raw LLM callable or a Hermes AIAgent for extraction.
    """

    def __init__(self, llm_call: LLMCallFn | None = None):
        self._llm_call = llm_call

    def set_llm_call(self, fn: LLMCallFn) -> None:
        self._llm_call = fn

    async def _invoke_llm(self, prompt: str) -> str:
        """Call injected LLM fn; accept sync or async implementations."""
        if not self._llm_call:
            return ""
        result = self._llm_call(prompt)
        if inspect.isawaitable(result):
            return await result
        return str(result)

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

        raw = await self._invoke_llm(prompt)
        data = _parse_json_from_response(raw)
        if not data:
            return 0

        updates = data.get("updates", [])
        if not isinstance(updates, list):
            return 0

        corpus = _build_existing_memory_corpus(butler_memory, project_memory)
        applied = 0
        skipped_dup = 0
        for upd in updates:
            target = upd.get("target", "")
            content = upd.get("content", "")
            section = upd.get("section", "")
            if not content:
                continue

            if memory_update_is_duplicate(content, corpus):
                skipped_dup += 1
                logger.debug("Post-session skip duplicate memory: %s", content[:80])
                continue

            try:
                if target == "butler" and butler_memory:
                    butler_memory.profile.add(content)
                    try:
                        butler_memory.sync_profile_vectors()
                    except Exception as exc:
                        logger.debug("Profile vector sync after post_session: %s", exc)
                    applied += 1
                    corpus = _build_existing_memory_corpus(butler_memory, project_memory)
                elif target == "project" and project_memory and section:
                    canon = _normalize_project_section(section)
                    cls_result = project_memory.markdown.append(canon, content)
                    sem = (
                        getattr(butler_memory, "semantic", None) if butler_memory else None
                    )
                    from butler.memory.semantic_project import (
                        resolve_project_display_name,
                        sync_project_append_vectors,
                    )

                    proj_name = (project_name or "").strip() or resolve_project_display_name(
                        project_memory
                    )
                    sync_project_append_vectors(
                        sem, proj_name, canon, content, cls_result
                    )
                    applied += 1
                    corpus = _build_existing_memory_corpus(butler_memory, project_memory)
                elif target == "experience" and butler_memory:
                    row_id = butler_memory.experience.add(
                        project=project_name, category="experience", content=content,
                    )
                    from butler.memory.semantic_index import index_experience_row

                    index_experience_row(
                        getattr(butler_memory, "semantic", None),
                        row_id,
                        project=project_name,
                        category="experience",
                        content=content,
                    )
                    applied += 1
                    corpus = _build_existing_memory_corpus(butler_memory, project_memory)
            except Exception as e:
                logger.warning("Memory update error: %s", e)

        if skipped_dup:
            logger.info("Post-session skipped %d duplicate memory update(s)", skipped_dup)
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

        raw = await self._invoke_llm(prompt)
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
