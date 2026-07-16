"""ConversationState — structured task state for multi-turn dialogues.

This module provides a structured conversation state object that persists
across turns, ensuring that task context is not lost even when message
compression removes earlier messages from the conversation history.

Key features:
- Current task summary with goal tracking
- Decision history (rolling window of 30)
- Files modified in this conversation
- Current plan steps
- Open questions to resolve
- Rolling window of last N turn summaries (20)
- Chapter summaries (every 10 turns)
- Task tree structure (project → milestone → task → subtask)
- Development context (branch, build status, pending todos)
- Semantic embedding integration for cold memory
- Token budget-aware system reminder generation
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional, cast

try:
    from butler.memory.semantic_memory import get_semantic_memory, CHROMADB_AVAILABLE
except ImportError:
    CHROMADB_AVAILABLE = False
    get_semantic_memory = lambda: None

try:
    from butler.memory.hybrid_retriever import get_hybrid_retriever
except ImportError:
    get_hybrid_retriever = lambda: None

try:
    from butler.memory.knowledge_graph import get_knowledge_graph
    from butler.memory.triplets import extract_triplets_from_text
    KG_AVAILABLE = True
except ImportError:
    KG_AVAILABLE = False
    get_knowledge_graph = lambda: None
    extract_triplets_from_text = lambda x, **kwargs: []


@dataclass
class TurnSummary:
    turn_number: int
    user_intent: str
    assistant_action: str
    result_summary: str
    files_touched: list[str] = field(default_factory=list)


@dataclass
class ConversationDecision:
    turn_number: int
    decision: str
    rationale: str
    outcome: str = ""


@dataclass
class ChapterSummary:
    chapter_number: int
    start_turn: int
    end_turn: int
    summary: str
    key_decisions: list[str] = field(default_factory=list)
    key_files: list[str] = field(default_factory=list)
    key_technologies: list[str] = field(default_factory=list)


@dataclass
class FileChange:
    path: str
    operation: str
    description: str
    turn_number: int


@dataclass
class TaskNode:
    id: str
    title: str
    status: str = "pending"
    description: str = ""
    parent_id: str | None = None
    children: list["TaskNode"] = field(default_factory=list)
    turn_created: int = 0
    turn_completed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "description": self.description,
            "parent_id": self.parent_id,
            "turn_created": self.turn_created,
            "turn_completed": self.turn_completed,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskNode":
        node = cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            status=data.get("status", "pending"),
            description=data.get("description", ""),
            parent_id=data.get("parent_id"),
            turn_created=data.get("turn_created", 0),
            turn_completed=data.get("turn_completed", 0),
        )
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            node.children.append(child)
        return node


@dataclass
class ConversationState:
    current_task_summary: str = ""
    decisions_made: list[ConversationDecision] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    current_plan_steps: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    turn_summaries: list[TurnSummary] = field(default_factory=list)
    conversation_goal: str = ""

    chapter_summaries: list[ChapterSummary] = field(default_factory=list)
    current_branch: str = ""
    pending_todos: list[str] = field(default_factory=list)
    last_build_status: str = ""
    file_change_log: list[FileChange] = field(default_factory=list)
    task_tree: TaskNode | None = None
    
    key_technologies: list[str] = field(default_factory=list)

    _conversation_id: str = "default"
    _max_turn_summaries: int = 20
    
    _reminder_cache: str = ""
    _reminder_cache_turn: int = 0
    _max_decisions: int = 30
    _max_chapters: int = 10
    _max_file_changes: int = 50
    _max_open_questions: int = 15
    _max_plan_steps: int = 20
    _max_technologies: int = 20

    @property
    def is_empty(self) -> bool:
        return (
            not self.current_task_summary
            and not self.decisions_made
            and not self.files_modified
            and not self.current_plan_steps
            and not self.open_questions
            and not self.turn_summaries
            and not self.conversation_goal
            and not self.chapter_summaries
            and not self.file_change_log
        )

    def add_turn_summary(
        self,
        turn_number: int,
        user_intent: str,
        assistant_action: str,
        result_summary: str,
        files_touched: list[str] | None = None,
        persist_to_external: bool = True,
    ) -> None:
        summary = TurnSummary(
            turn_number=turn_number,
            user_intent=user_intent[:500],
            assistant_action=assistant_action[:500],
            result_summary=result_summary[:500],
            files_touched=files_touched or [],
        )
        self.turn_summaries.append(summary)
        if len(self.turn_summaries) > self._max_turn_summaries:
            self.turn_summaries = self.turn_summaries[-self._max_turn_summaries :]
        for f in files_touched or []:
            if f not in self.files_modified:
                self.files_modified.append(f)
        
        if persist_to_external and CHROMADB_AVAILABLE:
            semantic_memory = get_semantic_memory()
            semantic_memory.add_turn_summary(
                turn_number=turn_number,
                user_intent=user_intent,
                assistant_action=assistant_action,
                result_summary=result_summary,
                conversation_id=self._conversation_id,
                files_touched=files_touched,
            )

    def add_decision(
        self,
        turn_number: int,
        decision: str,
        rationale: str,
        outcome: str = "",
    ) -> None:
        dec = ConversationDecision(
            turn_number=turn_number,
            decision=decision[:300],
            rationale=rationale[:500],
            outcome=outcome[:300],
        )
        self.decisions_made.append(dec)
        if len(self.decisions_made) > self._max_decisions:
            self.decisions_made = self.decisions_made[-self._max_decisions :]

    def add_chapter_summary(
        self,
        chapter_number: int,
        start_turn: int,
        end_turn: int,
        summary: str,
        key_decisions: list[str] | None = None,
        key_files: list[str] | None = None,
        key_technologies: list[str] | None = None,
        persist_to_external: bool = True,
    ) -> None:
        chapter = ChapterSummary(
            chapter_number=chapter_number,
            start_turn=start_turn,
            end_turn=end_turn,
            summary=summary[:1000],
            key_decisions=(key_decisions or [])[:5],
            key_files=(key_files or [])[:10],
            key_technologies=(key_technologies or [])[:10],
        )
        self.chapter_summaries.append(chapter)
        if len(self.chapter_summaries) > self._max_chapters:
            self.chapter_summaries = self.chapter_summaries[-self._max_chapters :]
        
        for tech in key_technologies or []:
            self.add_technology(tech)
        
        if persist_to_external and CHROMADB_AVAILABLE:
            semantic_memory = get_semantic_memory()
            semantic_memory.add_chapter_summary(
                chapter_number=chapter_number,
                start_turn=start_turn,
                end_turn=end_turn,
                summary=summary,
                conversation_id=self._conversation_id,
                key_decisions=key_decisions,
                key_files=key_files,
                key_technologies=key_technologies,
            )
        
        if persist_to_external and KG_AVAILABLE:
            kg = get_knowledge_graph()
            triplets = extract_triplets_from_text(summary, max_triplets=6)
            for triplet in triplets:
                kg.add_triple(triplet["subject"], triplet["relation"], triplet["object"])
            
            for tech in key_technologies or []:
                kg.add_entity(tech, tech, "technology")
            
            for file_name in key_files or []:
                kg.add_entity(file_name, file_name, "file")

    def add_technology(self, technology: str) -> None:
        if technology and technology not in self.key_technologies:
            self.key_technologies.append(technology)
            if len(self.key_technologies) > self._max_technologies:
                self.key_technologies = self.key_technologies[-self._max_technologies :]

    def add_file_change(self, path: str, operation: str, description: str, turn_number: int) -> None:
        change = FileChange(
            path=path,
            operation=operation[:20],
            description=description[:200],
            turn_number=turn_number,
        )
        self.file_change_log.append(change)
        if len(self.file_change_log) > self._max_file_changes:
            self.file_change_log = self.file_change_log[-self._max_file_changes :]

    def update_task_summary(self, new_summary: str) -> None:
        self.current_task_summary = new_summary[:1000]

    def update_conversation_goal(self, goal: str) -> None:
        self.conversation_goal = goal[:500]

    def add_plan_step(self, step: str) -> None:
        if step not in self.current_plan_steps:
            self.current_plan_steps.append(step[:200])
            if len(self.current_plan_steps) > self._max_plan_steps:
                self.current_plan_steps = self.current_plan_steps[-self._max_plan_steps :]

    def remove_plan_step(self, step: str) -> None:
        if step in self.current_plan_steps:
            self.current_plan_steps.remove(step)

    def add_open_question(self, question: str) -> None:
        if question not in self.open_questions:
            self.open_questions.append(question[:200])
            if len(self.open_questions) > self._max_open_questions:
                self.open_questions = self.open_questions[-self._max_open_questions :]

    def resolve_open_question(self, question: str) -> None:
        if question in self.open_questions:
            self.open_questions.remove(question)

    def add_pending_todo(self, todo: str) -> None:
        if todo not in self.pending_todos:
            self.pending_todos.append(todo[:300])

    def remove_pending_todo(self, todo: str) -> None:
        if todo in self.pending_todos:
            self.pending_todos.remove(todo)

    def find_task_by_id(self, task_id: str, node: TaskNode | None = None) -> TaskNode | None:
        node = node or self.task_tree
        if node is None:
            return None
        if node.id == task_id:
            return node
        for child in node.children:
            found = self.find_task_by_id(task_id, child)
            if found:
                return found
        return None

    def add_task(
        self,
        task_id: str,
        title: str,
        status: str = "pending",
        description: str = "",
        parent_id: str | None = None,
        turn_created: int = 0,
    ) -> None:
        if self.task_tree is None:
            self.task_tree = TaskNode(id="root", title="Project")
        if parent_id:
            parent = self.find_task_by_id(parent_id)
            if parent:
                parent.children.append(TaskNode(
                    id=task_id,
                    title=title[:200],
                    status=status,
                    description=description[:500],
                    parent_id=parent_id,
                    turn_created=turn_created,
                ))
        else:
            self.task_tree.children.append(TaskNode(
                id=task_id,
                title=title[:200],
                status=status,
                description=description[:500],
                turn_created=turn_created,
            ))

    def update_task_status(self, task_id: str, status: str, turn_completed: int = 0) -> bool:
        task = self.find_task_by_id(task_id)
        if task:
            task.status = status
            if status == "completed" and turn_completed:
                task.turn_completed = turn_completed
            return True
        return False

    def _estimate_tokens(self, text: str) -> int:
        cjk = sum(1 for ch in text if (0x4E00 <= ord(ch) <= 0x9FFF))
        ascii_len = len(text) - cjk
        return int(ascii_len / 4 + cjk * 1.3)

    def to_system_reminder(self, token_budget: int = 2000) -> str:
        if self.is_empty:
            return ""

        current_turn = len(self.turn_summaries)
        if self._reminder_cache and self._reminder_cache_turn == current_turn:
            return self._reminder_cache

        sections: list[tuple[int, str]] = []
        total_tokens = 0

        if self.conversation_goal:
            content = f"**对话目标**: {self.conversation_goal}"
            sections.append((100, content))
            total_tokens += self._estimate_tokens(content)

        if self.current_task_summary:
            content = f"**当前任务**: {self.current_task_summary}"
            sections.append((90, content))
            total_tokens += self._estimate_tokens(content)

        if self.current_plan_steps:
            steps = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(self.current_plan_steps))
            content = f"**执行计划**:\n{steps}"
            sections.append((80, content))
            total_tokens += self._estimate_tokens(content)

        if self.open_questions:
            questions = "\n".join(f"  - {q}" for q in self.open_questions)
            content = f"**待决问题**:\n{questions}"
            sections.append((70, content))
            total_tokens += self._estimate_tokens(content)

        if self.current_branch:
            content = f"**当前分支**: {self.current_branch}"
            sections.append((65, content))
            total_tokens += self._estimate_tokens(content)

        if self.last_build_status:
            content = f"**构建状态**: {self.last_build_status}"
            sections.append((60, content))
            total_tokens += self._estimate_tokens(content)

        if self.pending_todos:
            todos = "\n".join(f"  - {t}" for t in self.pending_todos[:5])
            content = f"**待办事项**:\n{todos}"
            sections.append((55, content))
            total_tokens += self._estimate_tokens(content)

        if self.key_technologies:
            techs = ", ".join(self.key_technologies)
            content = f"**技术栈**: {techs}"
            sections.append((52, content))
            total_tokens += self._estimate_tokens(content)

        if self.files_modified:
            files = ", ".join(self.files_modified[-15:])
            content = f"**已修改文件**: {files}"
            sections.append((50, content))
            total_tokens += self._estimate_tokens(content)

        if self.decisions_made:
            recent_decisions = self.decisions_made[-5:]
            dec_lines = "\n".join(
                f"  - [{d.turn_number}] {d.decision}" for d in recent_decisions
            )
            content = f"**关键决策**:\n{dec_lines}"
            sections.append((40, content))
            total_tokens += self._estimate_tokens(content)

        if self.chapter_summaries:
            chapters_text = ""
            for ch in self.chapter_summaries[-3:]:
                tech_text = f" 技术:[{', '.join(ch.key_technologies[:5])}]" if ch.key_technologies else ""
                chapters_text += f"\n**章节 {ch.chapter_number} (Turn {ch.start_turn}-{ch.end_turn})**: {ch.summary[:200]}{tech_text}"
            content = f"**章节摘要**:{chapters_text}"
            sections.append((30, content))
            total_tokens += self._estimate_tokens(content)

        if CHROMADB_AVAILABLE and self.conversation_goal:
            semantic_memory = get_semantic_memory()
            relevant_context = semantic_memory.get_relevant_context(
                query=self.conversation_goal,
                conversation_id=self._conversation_id,
                max_context_chars=500,
            )
            if relevant_context:
                content = f"**历史上下文**: {relevant_context}"
                sections.append((25, content))
                total_tokens += self._estimate_tokens(content)

        hybrid_retriever = get_hybrid_retriever()
        if hybrid_retriever and self.conversation_goal:
            kg_context = hybrid_retriever.get_context(
                query=self.conversation_goal,
                conversation_id=self._conversation_id,
            )
            if kg_context:
                content = f"**知识图谱**: {kg_context}"
                sections.append((28, content))
                total_tokens += self._estimate_tokens(content)

        if self.turn_summaries:
            recent = self.turn_summaries[-5:]
            turns_text = ""
            for ts in recent:
                turns_text += f"\n**Turn {ts.turn_number}**: 用户={ts.user_intent[:100]}, 操作={ts.assistant_action[:100]}"
            content = f"**最近轮次**:{turns_text}"
            sections.append((20, content))
            total_tokens += self._estimate_tokens(content)

        sections.sort(key=lambda x: x[0], reverse=True)

        if total_tokens <= token_budget:
            return "\n\n".join(s[1] for s in sections)

        selected: list[str] = []
        remaining = token_budget

        for priority, content in sections:
            tokens = self._estimate_tokens(content)
            if remaining >= tokens:
                selected.append(content)
                remaining -= tokens
            else:
                if priority >= 60:
                    truncated = content[: int(remaining * 4 / 1.3)]
                    if truncated:
                        selected.append(truncated + "...")
                        remaining = 0

        result = "\n\n".join(selected)
        self._reminder_cache = result
        self._reminder_cache_turn = len(self.turn_summaries)
        return result

    def to_compact_anchor(self) -> str:
        if self.is_empty:
            return ""

        parts: list[str] = []

        if self.conversation_goal:
            parts.append(f"目标: {self.conversation_goal[:150]}")

        if self.current_task_summary:
            parts.append(f"任务: {self.current_task_summary[:150]}")

        if self.files_modified:
            parts.append(f"修改: {', '.join(self.files_modified[:5])}")

        if self.open_questions:
            parts.append(f"待决: {', '.join(self.open_questions[:3])}")

        if self.current_branch:
            parts.append(f"分支: {self.current_branch}")

        if self.last_build_status:
            parts.append(f"构建: {self.last_build_status}")

        return " | ".join(parts)

    def to_full_state(self) -> dict[str, Any]:
        return {
            "conversation_goal": self.conversation_goal,
            "current_task_summary": self.current_task_summary,
            "current_plan_steps": self.current_plan_steps,
            "open_questions": self.open_questions,
            "current_branch": self.current_branch,
            "last_build_status": self.last_build_status,
            "pending_todos": self.pending_todos,
            "files_modified": self.files_modified,
            "key_technologies": self.key_technologies,
            "decisions_made": [
                {"turn_number": d.turn_number, "decision": d.decision, "rationale": d.rationale}
                for d in self.decisions_made
            ],
            "turn_summaries": [
                {"turn_number": t.turn_number, "user_intent": t.user_intent,
                 "assistant_action": t.assistant_action, "result_summary": t.result_summary,
                 "files_touched": t.files_touched}
                for t in self.turn_summaries
            ],
            "chapter_summaries": [
                {"chapter_number": c.chapter_number, "start_turn": c.start_turn,
                 "end_turn": c.end_turn, "summary": c.summary,
                 "key_decisions": c.key_decisions, "key_files": c.key_files,
                 "key_technologies": c.key_technologies}
                for c in self.chapter_summaries
            ],
            "file_change_log": [
                {"path": f.path, "operation": f.operation, "description": f.description,
                 "turn_number": f.turn_number}
                for f in self.file_change_log
            ],
            "task_tree": self.task_tree.to_dict() if self.task_tree else None,
        }

    def reset(self) -> None:
        self.current_task_summary = ""
        self.decisions_made.clear()
        self.files_modified.clear()
        self.current_plan_steps.clear()
        self.open_questions.clear()
        self.turn_summaries.clear()
        self.conversation_goal = ""
        self.chapter_summaries.clear()
        self.current_branch = ""
        self.pending_todos.clear()
        self.last_build_status = ""
        self.file_change_log.clear()
        self.task_tree = None
        self.key_technologies.clear()
        self._reminder_cache = ""
        self._reminder_cache_turn = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationState":
        state = cls()
        state.conversation_goal = data.get("conversation_goal", "")
        state.current_task_summary = data.get("current_task_summary", "")
        state.current_plan_steps = data.get("current_plan_steps", [])
        state.open_questions = data.get("open_questions", [])
        state.current_branch = data.get("current_branch", "")
        state.last_build_status = data.get("last_build_status", "")
        state.pending_todos = data.get("pending_todos", [])
        state.files_modified = data.get("files_modified", [])
        state.key_technologies = data.get("key_technologies", [])
        
        for dec_data in data.get("decisions_made", []):
            state.add_decision(
                turn_number=dec_data.get("turn_number", 0),
                decision=dec_data.get("decision", ""),
                rationale=dec_data.get("rationale", ""),
                outcome=dec_data.get("outcome", ""),
            )
        
        for ts_data in data.get("turn_summaries", []):
            state.add_turn_summary(
                turn_number=ts_data.get("turn_number", 0),
                user_intent=ts_data.get("user_intent", ""),
                assistant_action=ts_data.get("assistant_action", ""),
                result_summary=ts_data.get("result_summary", ""),
                files_touched=ts_data.get("files_touched", []),
                persist_to_external=False,
            )
        
        for ch_data in data.get("chapter_summaries", []):
            state.add_chapter_summary(
                chapter_number=ch_data.get("chapter_number", 0),
                start_turn=ch_data.get("start_turn", 0),
                end_turn=ch_data.get("end_turn", 0),
                summary=ch_data.get("summary", ""),
                key_decisions=ch_data.get("key_decisions", []),
                key_files=ch_data.get("key_files", []),
                key_technologies=ch_data.get("key_technologies", []),
                persist_to_external=False,
            )
        
        for fc_data in data.get("file_change_log", []):
            state.add_file_change(
                path=fc_data.get("path", ""),
                operation=fc_data.get("operation", ""),
                description=fc_data.get("description", ""),
                turn_number=fc_data.get("turn_number", 0),
            )
        
        task_tree_data = data.get("task_tree")
        if task_tree_data:
            state.task_tree = TaskNode.from_dict(task_tree_data)
        
        return state


def build_conversation_reminder(state: ConversationState, token_budget: int = 2000) -> str:
    content = state.to_system_reminder(token_budget=token_budget)
    if not content:
        return ""
    return f"<conversation-state>\n{content}\n</conversation-state>"


__all__ = [
    "ConversationDecision",
    "ConversationState",
    "TurnSummary",
    "ChapterSummary",
    "FileChange",
    "TaskNode",
    "build_conversation_reminder",
]
