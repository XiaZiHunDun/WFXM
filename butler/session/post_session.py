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

from butler.memory.private_tags import strip_private_tags

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
6. 用户称呼/微信风格 → butler(profile)；项目决策 → project；
   勿把「默认项目名」写入 profile（由环境变量 BUTLER_DEFAULT_PROJECT 决定）
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
            except Exception as exc:
                logger.debug("build existing memory corpus skipped: %s", exc)
        exp = getattr(butler_memory, "experience", None)
        if exp is not None and hasattr(exp, "get_recent"):
            try:
                from butler.session.lifecycle import filter_non_conversation_experience

                for row in filter_non_conversation_experience(exp.get_recent(limit=40)):
                    parts.append(str(row.get("content") or ""))
            except Exception as exc:
                logger.debug("build existing memory corpus skipped: %s", exc)
    if project_memory is not None and hasattr(project_memory, "get_full_context"):
        try:
            parts.append(str(project_memory.get_full_context(max_lines=80) or ""))
        except Exception as exc:
            logger.debug("build existing memory corpus skipped: %s", exc)
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


def _persist_butler_memory(content: str, butler_memory: Any) -> None:
    """Persist a butler-target memory update. Raises on profile.add failure."""
    butler_memory.profile.add(content)
    try:
        butler_memory.sync_profile_vectors()
    except Exception as exc:
        logger.debug("Profile vector sync after post_session: %s", exc)


def _persist_project_memory(
    content: str,
    section: str,
    butler_memory: Any,
    project_memory: Any,
    project_name: str,
) -> None:
    """Persist a project-target memory update. Raises on markdown.append failure."""
    canon = _normalize_project_section(section)
    cls_result = project_memory.markdown.append(canon, content)
    sem = getattr(butler_memory, "semantic", None) if butler_memory else None
    from butler.memory.semantic_project import (
        resolve_project_display_name,
        sync_project_append_vectors,
    )

    proj_name = (project_name or "").strip() or resolve_project_display_name(
        project_memory
    )
    sync_project_append_vectors(sem, proj_name, canon, content, cls_result)


def _persist_experience_memory(
    content: str, butler_memory: Any, project_name: str
) -> None:
    """Persist an experience memory update. Raises on add_experience failure."""
    butler_memory.add_experience(
        project=project_name, category="experience", content=content,
    )


def _dispatch_memory_update(
    upd: dict, butler_memory: Any, project_memory: Any, project_name: str
) -> bool:
    """Apply one memory update. Returns True iff persisted. Raises on persistence errors."""
    target = upd.get("target", "")
    content = upd.get("content", "")
    section = upd.get("section", "")
    if target == "butler" and butler_memory:
        _persist_butler_memory(content, butler_memory)
        return True
    if target == "project" and project_memory and section:
        _persist_project_memory(
            content, section, butler_memory, project_memory, project_name
        )
        return True
    if target == "experience" and butler_memory:
        _persist_experience_memory(content, butler_memory, project_name)
        return True
    return False


def _process_memory_update(
    upd: dict,
    butler_memory: Any,
    project_memory: Any,
    project_name: str,
    corpus: str,
    errors: list[str] | None,
    idx: int,
) -> tuple[int, int, str]:
    """Process one LLM-suggested memory update.

    Returns ``(applied_delta, skipped_dup_delta, new_corpus)``.
    ``applied_delta`` is 1 when the update was persisted, else 0.
    ``skipped_dup_delta`` is 1 when the update was skipped as a duplicate.
    On persistence failure: ``logger.error(..., exc_info=exc)`` and append a
    per-item message to ``errors`` (when provided) so the failure surfaces in
    ``/诊断`` instead of being silently swallowed (R2-7).
    """
    target = upd.get("target", "")
    content = upd.get("content", "")
    if not content:
        return 0, 0, corpus
    content, fully_private = strip_private_tags(content)
    if fully_private or not content:
        logger.debug("Post-session skip fully private memory update: %s", target)
        return 0, 0, corpus
    if memory_update_is_duplicate(content, corpus):
        logger.debug("Post-session skip duplicate memory: %s", content[:80])
        return 0, 1, corpus
    upd_clean = {**upd, "content": content}
    try:
        if _dispatch_memory_update(upd_clean, butler_memory, project_memory, project_name):
            return 1, 0, _build_existing_memory_corpus(butler_memory, project_memory)
    except Exception as exc:
        logger.error("Post-session memory update %d failed", idx, exc_info=exc)
        if errors is not None:
            errors.append(f"Memory item {idx}: {exc}")
    return 0, 0, corpus


def _create_one_skill(
    s: Any, skill_manager: Any, errors: list[str] | None
) -> int:
    """Create one LLM-suggested skill via ``skill_manager``.

    Returns 1 when persisted, 0 otherwise (invalid shape or per-item failure).
    On failure: ``logger.error(..., exc_info=exc)`` and append a per-item
    message to ``errors`` so ``/诊断`` sees the failure (R2-7).
    """
    if not isinstance(s, dict) or not s.get("name") or not s.get("body"):
        return 0
    name = s.get("name", "?")
    try:
        skill_manager.create(
            name=str(s["name"]),
            description=str(s.get("description", "")),
            triggers=s.get("triggers", []),
            content=str(s["body"]),
        )
        logger.info("Extracted skill: %s", name)
        return 1
    except Exception as exc:
        logger.error(
            "Post-session skill creation failed: %s", name, exc_info=exc,
        )
        if errors is not None:
            errors.append(f"Skill {name}: {exc}")
        return 0


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
        """Run both memory and skill extraction channels.

        Result keys:
        - ``memory_updates`` / ``skills_extracted``: int counters (backward compat).
        - ``memory_failed`` / ``skills_failed``: per-item failure counters surfaced
          to ``/诊断`` (R2-7).
        - ``errors``: list of channel-level + per-item error messages.
        """
        if not self._llm_call or len(messages) < 4:
            return {
                "memory_updates": 0,
                "memory_failed": 0,
                "skills_extracted": 0,
                "skills_failed": 0,
                "errors": [],
            }

        result: dict = {
            "memory_updates": 0,
            "memory_failed": 0,
            "skills_extracted": 0,
            "skills_failed": 0,
            "errors": [],
        }

        await self._run_memory_channel(
            messages, butler_memory, project_memory, project_name, result,
        )
        await self._run_skill_channel(messages, skill_manager, project_name, result)
        await self._maybe_run_layered(messages, result)

        return result

    async def _run_memory_channel(
        self,
        messages: list[dict],
        butler_memory: Any,
        project_memory: Any,
        project_name: str,
        result: dict,
    ) -> None:
        """Run memory extraction; populate ``memory_updates``/``memory_failed``/``errors``."""
        chan_errors: list[str] = []
        try:
            result["memory_updates"] = await self._extract_memories(
                messages, butler_memory, project_memory, project_name,
                errors=chan_errors,
            )
        except Exception as exc:
            logger.error("Memory extraction failed", exc_info=exc)
            result["errors"].append(f"Memory: {exc}")
        result["memory_failed"] = len(chan_errors)
        result["errors"].extend(chan_errors)

    async def _run_skill_channel(
        self,
        messages: list[dict],
        skill_manager: Any,
        project_name: str,
        result: dict,
    ) -> None:
        """Run skill extraction; populate ``skills_extracted``/``skills_failed``/``errors``."""
        chan_errors: list[str] = []
        try:
            result["skills_extracted"] = await self._extract_skills(
                messages, skill_manager, project_name,
                errors=chan_errors,
            )
        except Exception as exc:
            logger.error("Skill extraction failed", exc_info=exc)
            result["errors"].append(f"Skill: {exc}")
        result["skills_failed"] = len(chan_errors)
        result["errors"].extend(chan_errors)

    async def _maybe_run_layered(
        self, messages: list[dict], result: dict
    ) -> None:
        """Best-effort layered post-session extraction (debug-logged on failure)."""
        try:
            from butler.session.post_session_layered import (
                extract_layered_summary,
                post_session_layered_enabled,
            )

            if post_session_layered_enabled():
                layers = await extract_layered_summary(messages, self._llm_call)
                for key in ("persona", "preference", "experience"):
                    result[key] = layers.get(key) or []
        except Exception as exc:
            logger.debug("Layered post-session skipped: %s", exc)

    async def _extract_memories(
        self,
        messages: list[dict],
        butler_memory: Any,
        project_memory: Any,
        project_name: str,
        *,
        errors: list[str] | None = None,
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
        for idx, upd in enumerate(updates):
            a, s, corpus = _process_memory_update(
                upd, butler_memory, project_memory, project_name,
                corpus, errors, idx,
            )
            applied += a
            skipped_dup += s

        if skipped_dup:
            logger.info("Post-session skipped %d duplicate memory update(s)", skipped_dup)
        return applied

    async def _extract_skills(
        self,
        messages: list[dict],
        skill_manager: Any,
        project_name: str,
        *,
        errors: list[str] | None = None,
    ) -> int:
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
            created += _create_one_skill(s, skill_manager, errors)
        return created
