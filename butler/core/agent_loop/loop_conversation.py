"""Loop conversation state management — handles conversation state, experience injection, and summaries."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.core.conversation_state import ConversationState, build_conversation_reminder
from butler.core.delegate_context import set_parent_callbacks, set_parent_messages, set_parent_system_prompt
from butler.core.steer import clear_steer
from butler.core.turn_summarizer import summarize_chapter, summarize_turn, _extract_file_changes
from butler.core.tool_call_limits import reset_tool_call_limiter_for_turn
from butler.memory.experience.retriever import ExperienceRetriever
from butler.memory.experience.writer import ExperienceWriter
from butler.memory.semantic_index import SemanticMemoryIndex, get_embedder
from butler.defaults.env_defaults import CONVERSATION_STATE_PERSIST_DEFAULT
from butler.tools.conversation_state_tools import load_conversation_state, persist_conversation_state

logger = logging.getLogger(__name__)


def _init_turn_state(loop: Any, steer_session: str) -> None:
    """Reset per-turn mutable state before the iteration loop."""
    clear_steer(steer_session)
    loop._primary_client = loop.client
    loop._fallback_index = 0
    loop._empty_retries = 0
    loop._truncation_retries = 0
    set_parent_callbacks(loop.callbacks)
    set_parent_system_prompt(loop.system_prompt)
    set_parent_messages(loop._messages)
    loop._tool_prefetch.clear()
    if loop._guardrails:
        loop._guardrails.reset_for_turn()
    reset_tool_call_limiter_for_turn()
    _init_conversation_state(loop)


def _init_conversation_state(loop: Any) -> None:
    """Initialize conversation state — lazy-load from disk on first turn."""
    if loop._conversation_state is None:
        restored = None
        if _should_restore_state():
            restored = load_conversation_state()

        if restored is not None:
            loop._conversation_state = restored
            loop._turn_count = len(restored.turn_summaries)
            loop.diagnostics["conversation_state_restored"] = True
        else:
            loop._conversation_state = ConversationState()


def _should_restore_state() -> bool:
    """Check if cross-session state restoration is enabled."""
    return os.getenv("BUTLER_CONVERSATION_STATE_PERSIST", CONVERSATION_STATE_PERSIST_DEFAULT) == "1"


def _persist_conversation_state(loop: Any) -> None:
    """Persist conversation state to disk for cross-session recovery."""
    if loop._conversation_state is None:
        return
    if not _should_restore_state():
        return
    persist_conversation_state(loop._conversation_state)


def _build_turn_ephemeral_system(loop: Any, ephemeral_system: str | None) -> str | None:
    """Build ephemeral system message with conversation state and experience injected."""
    parts: list[str] = []
    if ephemeral_system:
        parts.append(str(ephemeral_system))

    if loop._conversation_state:
        reminder = build_conversation_reminder(loop._conversation_state, token_budget=2000)
        if reminder:
            parts.append(reminder)

    def _inject_experience() -> str | None:
        try:
            retriever = ExperienceRetriever()

            recent_intents = []
            if loop._conversation_state:
                for turn in loop._conversation_state.turn_summaries[-5:]:
                    if turn.user_intent:
                        recent_intents.append(turn.user_intent)
            if not recent_intents:
                return None

            query = " ".join(recent_intents)[:500]
            experiences = retriever.retrieve("default", query, top_k=3)

            if not experiences:
                return None

            experience_lines = []
            for exp in experiences:
                content = exp.node.content if hasattr(exp.node, "content") else str(exp.node)
                source = exp.source if hasattr(exp, "source") else "experience"
                score = exp.score if hasattr(exp, "score") else 0.0
                if score > 0.3:
                    experience_lines.append(
                        f"[经验 {source} 得分={score:.2f}]: {content[:200]}"
                    )

            if experience_lines:
                loop.diagnostics["experience_injected"] = len(experience_lines)
                return "\n\n".join(
                    ["## 相关历史经验"] + experience_lines
                )
            return None
        except Exception as e:
            logger.debug("Experience injection failed: %s", e)
            return None

    experience_section = safe_best_effort(
        _inject_experience,
        label="agent_loop.experience_injection",
        default=None,
    )
    if experience_section:
        parts.append(experience_section)

    if not parts:
        return None
    return "\n\n".join(parts)


def _update_conversation_state(loop: Any, user_message: str, result: Any) -> None:
    """Update conversation state after each turn completes."""
    if loop._conversation_state is None:
        return

    diag = result.diagnostics if result.diagnostics else {}
    tool_calls_detail = diag.get("tool_calls_detail", [])

    files_touched: list[str] = []
    for tc in tool_calls_detail:
        name = str(tc.get("name", "") or "")
        args = tc.get("args", {}) or {}
        if name in ("read_file", "write_file", "patch", "delete_file"):
            file_path = str(args.get("file_path") or args.get("path") or "")
            if file_path:
                files_touched.append(file_path)

    file_changes = _extract_file_changes(tool_calls_detail)
    for fc in file_changes:
        if fc["path"]:
            loop._conversation_state.add_file_change(
                path=fc["path"],
                operation=fc["operation"],
                description=fc["description"],
                turn_number=loop._turn_count,
            )

    _auto_detect_branch_and_build_status(loop, tool_calls_detail, diag)

    summary = summarize_turn(
        user_message=user_message,
        assistant_response=result.final_response or "",
        tool_calls_detail=tool_calls_detail,
    )

    loop._conversation_state.add_turn_summary(
        turn_number=loop._turn_count,
        user_intent=summary["user_intent"],
        assistant_action=summary["assistant_action"],
        result_summary=summary["result_summary"],
        files_touched=files_touched,
    )

    if loop._turn_count == 1:
        loop._conversation_state.update_conversation_goal(user_message[:500])
        loop._conversation_state.update_task_summary(user_message[:500])

    _try_generate_chapter_summary(loop)
    _try_embed_chapter_to_semantic_memory(loop)

    def _write_experience() -> None:
        try:
            if not tool_calls_detail:
                return

            writer = ExperienceWriter()
            metadata = {
                "turn_number": loop._turn_count,
                "files_touched": files_touched[:10],
                "tool_calls": len(tool_calls_detail),
                "session_id": getattr(loop, "_session_id", ""),
            }

            for tc in tool_calls_detail[:5]:
                tc_name = str(tc.get("name", ""))
                tc.get("args", {}) or {}
                tc_result = str(tc.get("result", ""))[:500]

                if tc.get("success", True):
                    query_part = f"{user_message[:100]} -> {tc_name}"
                    result_part = tc_result or summary.get("result_summary", "")[:200]

                    writer.write(
                        query=query_part,
                        result=result_part,
                        metadata={**metadata, "tool_name": tc_name},
                    )

            loop.diagnostics["experience_written"] = len(tool_calls_detail)
        except Exception as e:
            logger.debug("Experience write failed: %s", e)

    safe_best_effort(
        _write_experience,
        label="agent_loop.experience_write",
    )

    loop.diagnostics["conversation_state"] = loop._conversation_state
    _persist_conversation_state(loop)


def _auto_detect_branch_and_build_status(
    loop: Any, tool_calls_detail: list[dict[str, Any]], diag: dict[str, Any]
) -> None:
    """Auto-detect git branch and build status from terminal tool outputs."""
    for tc in tool_calls_detail:
        name = str(tc.get("name", "") or "")
        args = tc.get("args", {}) or {}
        cmd = str(args.get("command", "") or "")

        if name == "terminal":
            if "git branch" in cmd or "git status" in cmd:
                output = str(args.get("output", "") or "")
                match = re.search(r"\* (.*)", output)
                if match:
                    loop._conversation_state.current_branch = match.group(1).strip()[:50]

            if ("pytest" in cmd or "python -m pytest" in cmd or
                "build" in cmd or "make" in cmd or "setup.py" in cmd):
                output = str(args.get("output", "") or "")
                if "FAILED" in output or "Error" in output or "error" in output:
                    loop._conversation_state.last_build_status = "FAILED"
                elif "passed" in output.lower() or "success" in output.lower():
                    loop._conversation_state.last_build_status = "PASSED"

    if "tool_results" in diag:
        for tr in diag["tool_results"]:
            if tr.get("tool_name") == "terminal":
                output = str(tr.get("result", "") or "")
                if loop._conversation_state.current_branch == "":
                    match = re.search(r"\* (.*)", output)
                    if match:
                        loop._conversation_state.current_branch = match.group(1).strip()[:50]
                if loop._conversation_state.last_build_status == "":
                    if "FAILED" in output or "Error" in output or "error" in output:
                        loop._conversation_state.last_build_status = "FAILED"
                    elif "passed" in output.lower() or "success" in output.lower():
                        loop._conversation_state.last_build_status = "PASSED"


def _try_generate_chapter_summary(loop: Any) -> None:
    """Generate a chapter summary every 10 turns."""
    if loop._turn_count % 10 != 0:
        return
    if loop._conversation_state is None:
        return

    chapter_number = loop._turn_count // 10
    start_turn = (chapter_number - 1) * 10 + 1
    end_turn = loop._turn_count

    summaries = []
    for i in range(start_turn, end_turn + 1):
        summary = loop._conversation_state.get_turn_summary(i)
        if summary:
            summaries.append(f"Turn {i}: {summary.user_intent or ''}")

    if summaries:
        chapter_text = "\n".join(summaries)
        chapter_summary = summarize_chapter(chapter_text)
        if chapter_summary:
            loop._conversation_state.add_chapter_summary(
                chapter_number=chapter_number,
                summary=chapter_summary,
            )
            loop.diagnostics["chapter_summary_generated"] = chapter_number


def _try_embed_chapter_to_semantic_memory(loop: Any) -> None:
    """Embed chapter summary to semantic memory for retrieval."""
    if loop._turn_count % 10 != 0:
        return
    if loop._conversation_state is None:
        return

    chapter_number = loop._turn_count // 10
    chapter_summary = loop._conversation_state.get_chapter_summary(chapter_number)
    if not chapter_summary:
        return

    try:
        index = SemanticMemoryIndex()
        embedder = get_embedder()
        if embedder is None:
            return

        embedding = embedder.embed(chapter_summary)
        index.add(
            text=chapter_summary,
            embedding=embedding,
            metadata={"chapter": chapter_number, "turn_count": loop._turn_count},
        )
        loop.diagnostics["chapter_embedded"] = chapter_number
    except Exception as e:
        logger.debug("Chapter embedding failed: %s", e)


__all__ = [
    "_init_turn_state",
    "_init_conversation_state",
    "_should_restore_state",
    "_persist_conversation_state",
    "_build_turn_ephemeral_system",
    "_update_conversation_state",
    "_auto_detect_branch_and_build_status",
    "_try_generate_chapter_summary",
    "_try_embed_chapter_to_semantic_memory",
]
