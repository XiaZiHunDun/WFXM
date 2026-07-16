"""LLM-assisted turn summarization.

Uses a lightweight LLM call (DeepSeek) to generate intelligent turn summaries
that capture the key intent, action, and outcome of each conversation turn.
Falls back to rule-based extraction when LLM is unavailable.

Also provides chapter summarization - every N turns, generate a consolidated
summary of the chapter's progress, key decisions, and file changes.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SUMMARIZE_SYSTEM_PROMPT = """你是一个对话摘要专家。用1-3句话概括用户意图、助手操作和结果。
格式严格如下（JSON）：
{"user_intent": "用户想做什么", "assistant_action": "助手做了什么", "result_summary": "结果如何"}
只输出JSON，不要其他内容。"""

_CHAPTER_SYSTEM_PROMPT = """你是一个软件开发项目的章节摘要专家。
请阅读以下多个对话轮次的摘要，生成一个阶段性章节摘要。

要求：
1. 总结本章节完成的主要工作
2. 列出关键决策（不超过5个）
3. 列出主要修改的文件（不超过10个）
4. 列出使用的关键技术/工具（不超过10个）
5. 用简洁专业的语言，中文输出

格式严格如下（JSON）：
{"summary": "章节总结", "key_decisions": ["决策1", "决策2"], "key_files": ["file1.py", "file2.py"], "key_technologies": ["技术1", "技术2"]}
只输出JSON，不要其他内容。"""

_SUMMARIZE_MAX_INPUT = 4000
_SUMMARIZE_TIMEOUT = 15


def _get_summarizer_config() -> tuple[str, str, str]:
    ds_key = os.getenv("DEEPSEEK_API_KEY", "")
    if ds_key:
        return ("deepseek", "deepseek-chat", ds_key)
    mm_key = os.getenv("MINIMAX_API_KEY", "")
    if mm_key:
        return ("minimax", "MiniMax-M3", mm_key)
    return ("", "", "")


def _create_client(provider: str, model: str, api_key: str) -> Any:
    if provider == "deepseek":
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1", timeout=_SUMMARIZE_TIMEOUT)
    elif provider == "minimax":
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url="https://api.minimax.chat/v1", timeout=_SUMMARIZE_TIMEOUT)
    return None


def _extract_file_changes(tool_calls_detail: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    changes = []
    if not tool_calls_detail:
        return changes

    for tc in tool_calls_detail[:10]:
        name = str(tc.get("name", ""))
        args = tc.get("args", {}) or {}
        operation = ""
        path = ""
        description = ""

        if name == "write_file":
            operation = "write"
            path = str(args.get("file_path") or args.get("path") or "")
            description = "创建/覆盖文件"
        elif name == "patch":
            operation = "patch"
            path = str(args.get("file_path") or args.get("path") or "")
            description = "修改文件内容"
        elif name == "delete_file":
            operation = "delete"
            path = str(args.get("file_path") or args.get("path") or "")
            description = "删除文件"
        elif name == "read_file":
            operation = "read"
            path = str(args.get("file_path") or args.get("path") or "")
            description = "读取文件"
        elif name == "terminal":
            operation = "terminal"
            cmd = str(args.get("command", "") or "")
            if cmd:
                description = f"执行命令: {cmd[:100]}"

        if path or description:
            changes.append({
                "operation": operation,
                "path": path,
                "description": description,
            })

    return changes


def _extract_tool_info(tool_calls_detail: list[dict[str, Any]] | None) -> str:
    if not tool_calls_detail:
        return ""

    file_changes = _extract_file_changes(tool_calls_detail)
    if file_changes:
        file_lines = []
        for fc in file_changes:
            if fc["path"]:
                file_lines.append(f"{fc['operation']}: {fc['path']}")
            elif fc["description"]:
                file_lines.append(fc["description"])
        return "\n文件操作: " + "\n".join(file_lines)

    tool_names = [str(tc.get("name", "")) for tc in tool_calls_detail[:5] if tc.get("name")]
    if tool_names:
        return f"\n工具调用: {', '.join(tool_names)}"

    return ""


def summarize_turn_with_llm(
    user_message: str,
    assistant_response: str,
    tool_calls_detail: list[dict[str, Any]] | None = None,
) -> Optional[dict[str, str]]:
    provider, model, api_key = _get_summarizer_config()
    if not provider:
        logger.debug("No LLM provider configured for summarization")
        return None

    try:
        client = _create_client(provider, model, api_key)
        if client is None:
            return None

        user_text = (user_message or "")[:_SUMMARIZE_MAX_INPUT]
        assistant_text = (assistant_response or "")[:_SUMMARIZE_MAX_INPUT]

        tool_info = _extract_tool_info(tool_calls_detail)

        prompt = f"用户消息:\n{user_text}\n\n助手回复:\n{assistant_text}{tool_info}"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.1,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        result = json.loads(content)
        return {
            "user_intent": str(result.get("user_intent", ""))[:500],
            "assistant_action": str(result.get("assistant_action", ""))[:500],
            "result_summary": str(result.get("result_summary", ""))[:500],
        }
    except Exception as exc:
        logger.debug("LLM summarization failed: %s", exc)
        return None


def summarize_turn_fallback(
    user_message: str,
    assistant_response: str,
    tool_calls_detail: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    intent = (user_message or "")[:200]
    action = (assistant_response or "")[:200]
    outcome = "completed"

    file_changes = _extract_file_changes(tool_calls_detail)
    if file_changes:
        action = "文件操作: " + ", ".join(fc["path"] or fc["description"] for fc in file_changes[:3])

    return {
        "user_intent": intent,
        "assistant_action": action,
        "result_summary": outcome,
    }


def summarize_turn(
    user_message: str,
    assistant_response: str,
    tool_calls_detail: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    result = summarize_turn_with_llm(user_message, assistant_response, tool_calls_detail)
    if result is not None:
        return result
    return summarize_turn_fallback(user_message, assistant_response, tool_calls_detail)


def summarize_chapter_with_llm(
    turn_summaries: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    provider, model, api_key = _get_summarizer_config()
    if not provider:
        logger.debug("No LLM provider configured for chapter summarization")
        return None

    try:
        client = _create_client(provider, model, api_key)
        if client is None:
            return None

        summary_texts = []
        for ts in turn_summaries:
            summary_texts.append(
                f"Turn {ts.get('turn_number', 0)}: 用户={ts.get('user_intent', '')[:150]}, "
                f"操作={ts.get('assistant_action', '')[:150]}, 结果={ts.get('result_summary', '')[:100]}"
            )

        prompt = "\n\n".join(summary_texts)[:8000]

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _CHAPTER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.1,
        )

        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        result = json.loads(content)
        return {
            "summary": str(result.get("summary", ""))[:1000],
            "key_decisions": [str(d)[:300] for d in result.get("key_decisions", [])[:5]],
            "key_files": [str(f)[:200] for f in result.get("key_files", [])[:10]],
            "key_technologies": [str(t)[:200] for t in result.get("key_technologies", [])[:10]],
        }
    except Exception as exc:
        logger.debug("LLM chapter summarization failed: %s", exc)
        return None


def summarize_chapter_fallback(turn_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    files_set: set[str] = set()
    decisions: list[str] = []
    technologies: set[str] = set()

    tech_keywords = [
        "FastAPI", "PostgreSQL", "Redis", "JWT", "WebSocket", "Celery",
        "Docker", "Kubernetes", "Prometheus", "Grafana", "ELK", "React",
        "Vue", "SQLAlchemy", "MongoDB", "RabbitMQ", "Airflow", "PySpark",
        "OpenAI", "LangChain", "ChromaDB", "Qdrant", "Agent", "LLM", "API"
    ]

    for ts in turn_summaries:
        if "files_touched" in ts:
            for f in ts["files_touched"]:
                files_set.add(str(f))
        if ts.get("assistant_action"):
            action = str(ts["assistant_action"])
            if "决定" in action or "decision" in action.lower():
                decisions.append(action[:200])
            for kw in tech_keywords:
                if kw.lower() in action.lower():
                    technologies.add(kw)
        if ts.get("user_intent"):
            intent = str(ts["user_intent"])
            for kw in tech_keywords:
                if kw.lower() in intent.lower():
                    technologies.add(kw)

    summary = f"完成了{len(turn_summaries)}个轮次的对话，涉及{len(files_set)}个文件"
    if decisions:
        summary += f"，做出了{len(decisions)}个关键决策"
    if technologies:
        summary += f"，使用了{', '.join(list(technologies)[:3])}等技术"

    return {
        "summary": summary[:1000],
        "key_decisions": decisions[:5],
        "key_files": list(files_set)[:10],
        "key_technologies": list(technologies)[:10],
    }


def summarize_chapter(turn_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    result = summarize_chapter_with_llm(turn_summaries)
    if result is not None:
        return result
    return summarize_chapter_fallback(turn_summaries)


__all__ = [
    "summarize_turn",
    "summarize_turn_fallback",
    "summarize_turn_with_llm",
    "summarize_chapter",
    "summarize_chapter_fallback",
    "summarize_chapter_with_llm",
    "_extract_file_changes",
]
