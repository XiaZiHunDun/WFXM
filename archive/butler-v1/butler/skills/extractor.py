"""SkillExtractor -- post-session automatic skill extraction.

After a conversation ends, analyzes the transcript for repeatable patterns
and proposes new skills via SkillManager (which handles similarity + merge).
"""

import json
import logging
import re
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

LLMCallFn = Callable[[str], Coroutine[Any, Any, str]]

EXTRACTION_PROMPT = """你是一个 Skill 提炼专家。请分析以下对话记录，识别其中可复用的操作策略或工作流程。

## 判断标准（严格遵守）
1. 必须是可复用的操作策略、分析框架或工作流程
2. 如果只是一次性的问答或信息查询，忽略
3. 个人偏好和信息应存入 memory 而非 skill
4. 工具调用的固定模式（如「先搜热榜 -> 分析 -> 推荐选题」）才值得提炼
5. 至少涉及 2 个以上的步骤或决策点才算工作流程
6. 已有的 skill（见下方列表）不需要重复提炼

## 范围判定 (scope)
- \"project\": 工作流程主要绑定当前代码仓/当前项目（默认）
- \"global\": 跨项目通用的方法论、与具体仓库无关的可复用流程
若不确定，选择 \"project\"。

## 已有 Skills
{existing_skills}

## 对话记录
{transcript}

## 输出格式
严格输出以下 JSON（不要输出其他内容）：
{{
  "skills": [
    {{
      "name": "skill-name-in-kebab-case",
      "description": "一句话描述这个 skill 的作用",
      "triggers": ["触发这个 skill 的用户语句片段"],
      "tools": ["skill 中用到的工具名"],
      "scope": "project",
      "body": "## 工作流程\\n\\n### 第一步：...\\n..."
    }}
  ]
}}

如果没有发现可提炼的 skill，返回 {{"skills": []}}"""


def _compress_transcript(messages: List[Dict[str, Any]], max_chars: int = 12000) -> str:
    """Compress session messages into a readable transcript."""
    parts = []
    total = 0

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue

        # Skip tool results longer than 500 chars
        if role == "tool" and len(content) > 500:
            tool_name = msg.get("tool_name", "unknown")
            content = f"[{tool_name}: {len(content)} chars result]"

        line = f"[{role.upper()}]: {content}"

        if total + len(line) > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                parts.append(line[:remaining] + "...[truncated]")
            break

        parts.append(line)
        total += len(line)

    return "\n\n".join(parts)


def _normalize_scope(raw: Any) -> str:
    s = str(raw or "project").strip().lower()
    if s in ("global", "project"):
        return s
    return "project"


class SkillExtractor:
    """Extracts reusable skills from session transcripts."""

    def __init__(self, llm_call: Optional[LLMCallFn] = None):
        self._llm_call = llm_call

    def set_llm_call(self, fn: LLMCallFn) -> None:
        self._llm_call = fn

    async def extract_from_messages(
        self,
        messages: List[Dict[str, Any]],
        existing_skill_names: List[str],
    ) -> List[Dict[str, Any]]:
        """Analyze messages and return candidate skills.

        Returns list of skill dicts with keys: name, description, triggers, tools, body, scope.
        Empty list if nothing worth extracting.
        """
        if not self._llm_call:
            logger.warning("SkillExtractor: no LLM call configured, skipping")
            return []

        if len(messages) < 4:
            logger.debug("Session too short for skill extraction (%d messages)", len(messages))
            return []

        transcript = _compress_transcript(messages)
        if len(transcript) < 200:
            return []

        existing_list = ", ".join(existing_skill_names) if existing_skill_names else "(none)"

        prompt = EXTRACTION_PROMPT.format(
            existing_skills=existing_list,
            transcript=transcript,
        )

        try:
            response = await self._llm_call(prompt)
            text = response.strip()

            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if not json_match:
                logger.debug("Extractor: no JSON in response")
                return []

            data = json.loads(json_match.group())
            skills = data.get("skills", [])

            if not isinstance(skills, list):
                return []

            valid = []
            for s in skills:
                if not isinstance(s, dict):
                    continue
                if not s.get("name") or not s.get("description") or not s.get("body"):
                    continue
                valid.append({
                    "name": str(s["name"]),
                    "description": str(s["description"]),
                    "triggers": [str(t) for t in s.get("triggers", [])] if isinstance(s.get("triggers"), list) else [],
                    "tools": [str(t) for t in s.get("tools", [])] if isinstance(s.get("tools"), list) else [],
                    "body": str(s["body"]),
                    "scope": _normalize_scope(s.get("scope")),
                })

            if valid:
                logger.info("Extracted %d candidate skill(s): %s", len(valid), [s["name"] for s in valid])
            else:
                logger.debug("No skills extracted from session")

            return valid[:2]

        except json.JSONDecodeError as e:
            logger.error("Extractor JSON parse error: %s", e)
            return []
        except Exception as e:
            logger.error("Extractor LLM error: %s", e)
            return []
