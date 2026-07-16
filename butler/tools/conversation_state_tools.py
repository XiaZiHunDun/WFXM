"""Conversation state tools — let the LLM read and update conversation state.

Provides tools:
- conversation_state_read: Get current conversation state (goal, plan, decisions, etc.)
- conversation_state_update: Update conversation state (add decision, plan step, task, etc.)
- conversation_state_search: Semantic search through historical turn summaries

Also provides cross-session persistence via JSON file storage.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from butler.core.conversation_state import ConversationState, TaskNode


_STATE_DIR = Path.home() / ".butler" / "conversation_states"
_STATE_FILE = _STATE_DIR / "current.json"


def persist_conversation_state(state: ConversationState) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "conversation_goal": state.conversation_goal,
        "current_task_summary": state.current_task_summary,
        "current_plan_steps": state.current_plan_steps,
        "open_questions": state.open_questions,
        "current_branch": state.current_branch,
        "last_build_status": state.last_build_status,
        "pending_todos": state.pending_todos,
        "files_modified": state.files_modified,
        "decisions_made": [
            {"turn_number": d.turn_number, "decision": d.decision, "rationale": d.rationale, "outcome": d.outcome}
            for d in state.decisions_made
        ],
        "turn_summaries": [
            {"turn_number": t.turn_number, "user_intent": t.user_intent,
             "assistant_action": t.assistant_action, "result_summary": t.result_summary,
             "files_touched": t.files_touched}
            for t in state.turn_summaries
        ],
        "chapter_summaries": [
            {"chapter_number": c.chapter_number, "start_turn": c.start_turn,
             "end_turn": c.end_turn, "summary": c.summary,
             "key_decisions": c.key_decisions, "key_files": c.key_files}
            for c in state.chapter_summaries
        ],
        "file_change_log": [
            {"path": f.path, "operation": f.operation, "description": f.description,
             "turn_number": f.turn_number}
            for f in state.file_change_log
        ],
        "task_tree": state.task_tree.to_dict() if state.task_tree else None,
    }
    with open(_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_conversation_state() -> ConversationState | None:
    if not _STATE_FILE.exists():
        return None
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = ConversationState(
            conversation_goal=data.get("conversation_goal", ""),
            current_task_summary=data.get("current_task_summary", ""),
            current_plan_steps=data.get("current_plan_steps", []),
            open_questions=data.get("open_questions", []),
            current_branch=data.get("current_branch", ""),
            last_build_status=data.get("last_build_status", ""),
            pending_todos=data.get("pending_todos", []),
            files_modified=data.get("files_modified", []),
        )
        for d in data.get("decisions_made", []):
            state.add_decision(
                turn_number=d.get("turn_number", 0),
                decision=d.get("decision", ""),
                rationale=d.get("rationale", ""),
                outcome=d.get("outcome", ""),
            )
        for t in data.get("turn_summaries", []):
            state.add_turn_summary(
                turn_number=t.get("turn_number", 0),
                user_intent=t.get("user_intent", ""),
                assistant_action=t.get("assistant_action", ""),
                result_summary=t.get("result_summary", ""),
                files_touched=t.get("files_touched", []),
            )
        for c in data.get("chapter_summaries", []):
            state.add_chapter_summary(
                chapter_number=c.get("chapter_number", 0),
                start_turn=c.get("start_turn", 0),
                end_turn=c.get("end_turn", 0),
                summary=c.get("summary", ""),
                key_decisions=c.get("key_decisions", []),
                key_files=c.get("key_files", []),
            )
        for f in data.get("file_change_log", []):
            state.add_file_change(
                path=f.get("path", ""),
                operation=f.get("operation", ""),
                description=f.get("description", ""),
                turn_number=f.get("turn_number", 0),
            )
        if data.get("task_tree"):
            state.task_tree = TaskNode.from_dict(data["task_tree"])
        return state
    except Exception:
        return None


def _format_task_tree(node: TaskNode | None, indent: int = 0) -> str:
    if node is None:
        return ""
    lines = []
    prefix = "  " * indent
    status_icon = {
        "completed": "[✓]",
        "in_progress": "[~]",
        "pending": "[ ]",
        "blocked": "[!]",
    }.get(node.status, "[?]")
    lines.append(f"{prefix}{status_icon} {node.title}")
    if node.description:
        lines.append(f"{prefix}  描述: {node.description[:100]}")
    for child in node.children:
        lines.append(_format_task_tree(child, indent + 1))
    return "\n".join(lines)


def tool_conversation_state_read(mode: str = "quick") -> str:
    """Read conversation state."""
    from butler.core.agent_loop import AgentLoop
    from butler.execution_context import get_current_orchestrator

    orch = get_current_orchestrator()
    loop: AgentLoop | None = None
    if orch is not None:
        loop = getattr(orch, "_loop", None)

    state: ConversationState | None = None
    if loop is not None and hasattr(loop, "_conversation_state"):
        state = loop._conversation_state
    else:
        state = load_conversation_state()

    if state is None:
        return json.dumps({"ok": False, "error": "No conversation state found"}, ensure_ascii=False)

    if mode == "full":
        return json.dumps(state.to_full_state(), ensure_ascii=False, indent=2)
    elif mode == "tasks":
        tree_text = _format_task_tree(state.task_tree) if state.task_tree else "无任务树"
        return f"任务树:\n{tree_text}"
    elif mode == "files":
        changes = "\n".join(
            f"  [{c.turn_number}] {c.operation} {c.path} - {c.description}"
            for c in state.file_change_log[-20:]
        )
        return f"文件变更历史:\n{changes}"
    elif mode == "decisions":
        decisions = "\n".join(
            f"  [{d.turn_number}] {d.decision} - {d.outcome or '进行中'}"
            for d in state.decisions_made[-10:]
        )
        return f"关键决策:\n{decisions}"
    elif mode == "chapters":
        chapters = "\n".join(
            f"  章节{c.chapter_number} (Turn {c.start_turn}-{c.end_turn}): {c.summary[:200]}"
            for c in state.chapter_summaries[-5:]
        )
        return f"章节摘要:\n{chapters}"
    else:
        return json.dumps({
            "ok": True,
            "conversation_goal": state.conversation_goal,
            "current_task_summary": state.current_task_summary,
            "current_plan_steps": state.current_plan_steps,
            "open_questions": state.open_questions[:5],
            "files_modified": state.files_modified[-10:],
            "current_branch": state.current_branch,
            "last_build_status": state.last_build_status,
            "pending_todos": state.pending_todos[:5],
            "turn_count": len(state.turn_summaries),
            "chapter_count": len(state.chapter_summaries),
        }, ensure_ascii=False)


def tool_conversation_state_update(
    action: str,
    **kwargs: Any,
) -> str:
    """Update conversation state."""
    from butler.core.agent_loop import AgentLoop
    from butler.execution_context import get_current_orchestrator

    orch = get_current_orchestrator()
    loop: AgentLoop | None = None
    if orch is not None:
        loop = getattr(orch, "_loop", None)

    state: ConversationState | None = None
    if loop is not None and hasattr(loop, "_conversation_state"):
        state = loop._conversation_state
    else:
        state = load_conversation_state()

    if state is None:
        state = ConversationState()

    try:
        if action == "add_decision":
            state.add_decision(
                turn_number=int(kwargs.get("turn_number", 0)),
                decision=str(kwargs.get("decision", "")),
                rationale=str(kwargs.get("rationale", "")),
                outcome=str(kwargs.get("outcome", "")),
            )
        elif action == "add_plan_step":
            state.add_plan_step(str(kwargs.get("step", "")))
        elif action == "remove_plan_step":
            state.remove_plan_step(str(kwargs.get("step", "")))
        elif action == "add_open_question":
            state.add_open_question(str(kwargs.get("question", "")))
        elif action == "resolve_open_question":
            state.resolve_open_question(str(kwargs.get("question", "")))
        elif action == "update_task_summary":
            state.update_task_summary(str(kwargs.get("summary", "")))
        elif action == "update_goal":
            state.update_conversation_goal(str(kwargs.get("goal", "")))
        elif action == "add_todo":
            state.add_pending_todo(str(kwargs.get("todo", "")))
        elif action == "remove_todo":
            state.remove_pending_todo(str(kwargs.get("todo", "")))
        elif action == "update_branch":
            state.current_branch = str(kwargs.get("branch", ""))
        elif action == "update_build_status":
            state.last_build_status = str(kwargs.get("status", ""))
        elif action == "add_task":
            state.add_task(
                task_id=str(kwargs.get("task_id", "")),
                title=str(kwargs.get("title", "")),
                status=str(kwargs.get("status", "pending")),
                description=str(kwargs.get("description", "")),
                parent_id=kwargs.get("parent_id"),
                turn_created=int(kwargs.get("turn_created", 0)),
            )
        elif action == "update_task_status":
            result = state.update_task_status(
                task_id=str(kwargs.get("task_id", "")),
                status=str(kwargs.get("status", "")),
                turn_completed=int(kwargs.get("turn_completed", 0)),
            )
            if not result:
                return json.dumps({"ok": False, "error": "Task not found"}, ensure_ascii=False)
        elif action == "add_file_change":
            state.add_file_change(
                path=str(kwargs.get("path", "")),
                operation=str(kwargs.get("operation", "")),
                description=str(kwargs.get("description", "")),
                turn_number=int(kwargs.get("turn_number", 0)),
            )
        elif action == "reset":
            state.reset()
        else:
            return json.dumps({"ok": False, "error": f"Unknown action: {action}"}, ensure_ascii=False)

        if loop is not None and hasattr(loop, "_conversation_state"):
            loop._conversation_state = state
        persist_conversation_state(state)

        return json.dumps({"ok": True, "action": action}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def tool_conversation_state_search(query: str, limit: int = 5, semantic_mode: bool = False) -> str:
    """Search through historical turn summaries and chapter summaries."""
    from butler.core.agent_loop import AgentLoop
    from butler.execution_context import get_current_orchestrator, get_current_session_key

    if semantic_mode:
        try:
            from butler.memory.semantic_index import SemanticMemoryIndex, get_embedder

            session_key = str(get_current_session_key() or "default")
            index = SemanticMemoryIndex(
                db_path=f"~/.butler/memory/semantic/{session_key}.db",
                embedder=get_embedder(),
            )
            results = index.search(query, limit=limit)
            index.close()
            if results:
                return json.dumps({"ok": True, "results": results, "retrieval": "semantic"}, ensure_ascii=False, indent=2)
        except Exception as exc:
            pass

    orch = get_current_orchestrator()
    loop: AgentLoop | None = None
    if orch is not None:
        loop = getattr(orch, "_loop", None)

    state: ConversationState | None = None
    if loop is not None and hasattr(loop, "_conversation_state"):
        state = loop._conversation_state
    else:
        state = load_conversation_state()

    if state is None:
        return json.dumps({"ok": False, "error": "No conversation state found"}, ensure_ascii=False)

    results = []

    if state.chapter_summaries:
        for ch in reversed(state.chapter_summaries):
            text = f"{ch.summary} {' '.join(ch.key_decisions)} {' '.join(ch.key_files)}".lower()
            if query.lower() in text:
                results.append({
                    "type": "chapter",
                    "chapter_number": ch.chapter_number,
                    "start_turn": ch.start_turn,
                    "end_turn": ch.end_turn,
                    "summary": ch.summary,
                    "key_decisions": ch.key_decisions,
                    "key_files": ch.key_files,
                })
            if len(results) >= limit:
                break

    if len(results) < limit and state.turn_summaries:
        for ts in reversed(state.turn_summaries):
            text = f"{ts.user_intent} {ts.assistant_action} {ts.result_summary}".lower()
            if query.lower() in text:
                results.append({
                    "type": "turn",
                    "turn_number": ts.turn_number,
                    "user_intent": ts.user_intent,
                    "assistant_action": ts.assistant_action,
                    "result_summary": ts.result_summary,
                    "files_touched": ts.files_touched,
                })
            if len(results) >= limit:
                break

    if not results and state.turn_summaries:
        query_lower = query.lower()
        for ts in reversed(state.turn_summaries):
            text = f"{ts.user_intent} {ts.assistant_action} {ts.result_summary}".lower()
            score = sum(1 for w in query_lower.split() if w in text)
            if score > 0:
                results.append({
                    "type": "turn",
                    "turn_number": ts.turn_number,
                    "user_intent": ts.user_intent,
                    "assistant_action": ts.assistant_action,
                    "result_summary": ts.result_summary,
                    "files_touched": ts.files_touched,
                    "score": score,
                })
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        results = results[:limit]

    return json.dumps({"ok": True, "results": results, "retrieval": "keyword"}, ensure_ascii=False, indent=2)


def register_conversation_state_tools(register_fn: Any) -> None:
    register_fn(
        name="conversation_state_read",
        description=(
            "读取当前对话状态，包含目标、任务、计划、决策、文件变更、任务树等信息。\n"
            "mode 参数可选值:\n"
            "- quick: 快速概览（默认）\n"
            "- full: 完整状态\n"
            "- tasks: 任务树详情\n"
            "- files: 文件变更历史\n"
            "- decisions: 关键决策\n"
            "- chapters: 章节摘要"
        ),
        schema={
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "description": "读取模式: quick/full/tasks/files/decisions/chapters",
                    "default": "quick",
                },
            },
        },
        handler=tool_conversation_state_read,
        toolset="conversation",
    )

    register_fn(
        name="conversation_state_update",
        description=(
            "更新对话状态。action 参数指定操作类型:\n"
            "- add_decision: 添加决策 (turn_number, decision, rationale, outcome)\n"
            "- add_plan_step: 添加计划步骤 (step)\n"
            "- remove_plan_step: 移除计划步骤 (step)\n"
            "- add_open_question: 添加待决问题 (question)\n"
            "- resolve_open_question: 解决待决问题 (question)\n"
            "- update_task_summary: 更新任务摘要 (summary)\n"
            "- update_goal: 更新对话目标 (goal)\n"
            "- add_todo: 添加待办 (todo)\n"
            "- remove_todo: 移除待办 (todo)\n"
            "- update_branch: 更新当前分支 (branch)\n"
            "- update_build_status: 更新构建状态 (status)\n"
            "- add_task: 添加任务到任务树 (task_id, title, status, description, parent_id, turn_created)\n"
            "- update_task_status: 更新任务状态 (task_id, status, turn_completed)\n"
            "- add_file_change: 添加文件变更记录 (path, operation, description, turn_number)\n"
            "- reset: 重置所有状态"
        ),
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": [
                        "add_decision", "add_plan_step", "remove_plan_step",
                        "add_open_question", "resolve_open_question",
                        "update_task_summary", "update_goal",
                        "add_todo", "remove_todo",
                        "update_branch", "update_build_status",
                        "add_task", "update_task_status",
                        "add_file_change", "reset",
                    ],
                },
                "turn_number": {"type": "integer", "description": "轮次号"},
                "decision": {"type": "string", "description": "决策内容"},
                "rationale": {"type": "string", "description": "决策理由"},
                "outcome": {"type": "string", "description": "决策结果"},
                "step": {"type": "string", "description": "计划步骤"},
                "question": {"type": "string", "description": "待决问题"},
                "summary": {"type": "string", "description": "任务摘要"},
                "goal": {"type": "string", "description": "对话目标"},
                "todo": {"type": "string", "description": "待办事项"},
                "branch": {"type": "string", "description": "当前分支"},
                "status": {"type": "string", "description": "状态"},
                "task_id": {"type": "string", "description": "任务ID"},
                "title": {"type": "string", "description": "任务标题"},
                "description": {"type": "string", "description": "任务描述"},
                "parent_id": {"type": "string", "description": "父任务ID"},
                "turn_created": {"type": "integer", "description": "创建轮次"},
                "turn_completed": {"type": "integer", "description": "完成轮次"},
                "path": {"type": "string", "description": "文件路径"},
                "operation": {"type": "string", "description": "操作类型"},
            },
            "required": ["action"],
        },
        handler=tool_conversation_state_update,
        toolset="conversation",
    )

    register_fn(
        name="conversation_state_search",
        description=(
            "搜索历史对话轮次摘要，支持关键词匹配。\n"
            "query: 搜索关键词\n"
            "limit: 返回结果数量（默认5）"
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回数量", "default": 5},
            },
            "required": ["query"],
        },
        handler=tool_conversation_state_search,
        toolset="conversation",
    )


__all__ = [
    "persist_conversation_state",
    "load_conversation_state",
    "tool_conversation_state_read",
    "tool_conversation_state_update",
    "tool_conversation_state_search",
    "register_conversation_state_tools",
]
