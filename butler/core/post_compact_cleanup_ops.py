"""Post-compact anchor best-effort builders (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.core.agents_md_sections import extract_agents_md_sections
from butler.core.compaction_phase import should_skip_post_compact_reanchor
from butler.core.design_md_sections import extract_design_md_sections
from butler.core.fact_extraction import format_facts_for_anchor, record_fact_anchor_metrics
from butler.core.read_state import get_recent_edit_paths
from butler.core.research_simplicity import format_simplicity_anchor
from butler.core.session_todos import format_open_todos_anchor, session_todos_enabled
from butler.execution_context import (
    get_audit_session_key,
    get_current_orchestrator,
    get_current_session_key,
)
from butler.runtime.task_store import list_recent_tasks
from butler.session.lifecycle import prefetch_turn_memory
from butler.tools.registry import get_tool_audit_events

def build_core_anchors_safe(
    diagnostics: dict[str, Any] | None,
    *,
    role: str,
) -> list[str]:
    def _run() -> list[str]:

        parts: list[str] = []
        sk = str(get_current_session_key() or "").strip()
        tasks = list_recent_tasks(sk, limit=3)
        if tasks:
            lines = [
                f"- {t.get('task_id', '?')}: {t.get('status', '?')} "
                f"{(t.get('task_preview') or '')[:100]}"
                for t in tasks
            ]
            parts.append("## Active tasks\n" + "\n".join(lines))
            if diagnostics is not None:
                diagnostics["post_compact_tasks"] = len(lines)


        if session_todos_enabled():
            todo_anchor = format_open_todos_anchor(sk)
            if todo_anchor:
                parts.append(todo_anchor)
                if diagnostics is not None:
                    diagnostics["post_compact_session_todos"] = todo_anchor.count("\n")

        orch = get_current_orchestrator()
        if orch is not None:
            mem = prefetch_turn_memory(
                orch,
                "[post-compact-reanchor]",
                role=role,
                use_cache=False,
                diagnostics=diagnostics,
            )
            if mem and mem.strip():
                parts.append("## Memory anchor\n" + mem.strip()[:4000])

            inject = getattr(orch, "inject_skill_context", None)
            if callable(inject):
                skill = inject("项目维护与当前会话上下文", diagnostics=diagnostics)
                if skill and str(skill).strip():
                    parts.append("## Skills anchor\n" + str(skill).strip()[:2000])
        return parts

    result = safe_best_effort(
        _run,
        label="post_compact_cleanup.core_anchors",
        default=[],
    )
    if not isinstance(result, list):
        if diagnostics is not None:
            diagnostics["post_compact_anchor_error"] = "core_anchors_skipped"
        return []
    return result


def agents_md_block_safe(diagnostics: dict[str, Any] | None) -> str:
    def _run() -> str:

        return str(extract_agents_md_sections() or "")

    block = safe_best_effort(_run, label="post_compact_cleanup.agents_md", default="")
    if block and diagnostics is not None:
        diagnostics["post_compact_agents_sections"] = len(block)
    return block if isinstance(block, str) else ""


def design_md_block_safe(diagnostics: dict[str, Any] | None) -> str:
    def _run() -> str:

        return str(extract_design_md_sections() or "")

    block = safe_best_effort(_run, label="post_compact_cleanup.design_md", default="")
    if block and diagnostics is not None:
        diagnostics["post_compact_design_sections"] = len(block)
    return block if isinstance(block, str) else ""


def simplicity_anchor_safe(diagnostics: dict[str, Any] | None) -> str:
    def _run() -> str:

        return str(format_simplicity_anchor() or "")

    block = safe_best_effort(_run, label="post_compact_cleanup.simplicity", default="")
    if block and diagnostics is not None:
        diagnostics["post_compact_simplicity"] = True
    return block if isinstance(block, str) else ""


def recent_files_block_safe(diagnostics: dict[str, Any] | None) -> str:
    def _run() -> str:

        recent = get_recent_edit_paths(limit=5)
        if not recent:
            return ""
        lines = [f"- {p}" for p in recent]
        return "## Recent edited files\n" + "\n".join(lines)

    block = safe_best_effort(_run, label="post_compact_cleanup.recent_files", default="")
    if block and diagnostics is not None:
        diagnostics["post_compact_recent_files"] = block.count("\n")
    return block if isinstance(block, str) else ""


def dev_changes_block_safe(diagnostics: dict[str, Any] | None) -> str:
    block = collect_dev_session_changes_safe()
    if block and diagnostics is not None:
        diagnostics["post_compact_dev_changes"] = True
    return block


def facts_anchor_block_safe(diagnostics: dict[str, Any] | None) -> str:
    def _run() -> str:

        sk = get_audit_session_key(fallback="_global")
        facts_block = format_facts_for_anchor(sk)
        if facts_block:
            record_fact_anchor_metrics(sk, diagnostics=diagnostics)
        return facts_block or ""

    block = safe_best_effort(_run, label="post_compact_cleanup.facts", default="")
    if block and diagnostics is not None:
        diagnostics["post_compact_facts"] = True
    return block if isinstance(block, str) else ""


def collect_dev_session_changes_safe() -> str:
    def _run() -> str:

        sk = get_audit_session_key(fallback="_global")
        events = get_tool_audit_events(limit=100, session_key=sk)
        return _format_dev_changes(events)

    result = safe_best_effort(
        _run,
        label="post_compact_cleanup.dev_changes",
        default="",
    )
    return result if isinstance(result, str) else ""


def _format_dev_changes(events: list) -> str:
    write_tools = {"write_file", "patch", "delete_file"}
    terminal_tools = {"terminal"}
    git_write_tools = {"git_add", "git_commit", "git_push"}

    written_files: list[str] = []
    terminal_cmds: list[str] = []
    git_ops: list[str] = []
    seen_files: set[str] = set()
    for ev in events:
        tool = ev.get("tool", "")
        args = ev.get("args") or {}
        if tool in write_tools:
            path = str(args.get("path") or args.get("file") or "").strip()
            if path and path not in seen_files:
                seen_files.add(path)
                action = {"write_file": "写入", "patch": "修改", "delete_file": "删除"}.get(tool, tool)
                written_files.append(f"  [{action}] {path}")
        elif tool in terminal_tools:
            cmd = str(args.get("command") or "").strip()[:80]
            if cmd:
                terminal_cmds.append(f"  $ {cmd}")
        elif tool in git_write_tools:
            if tool == "git_commit":
                msg = str(args.get("message") or "").strip()[:60]
                git_ops.append(f"  commit: {msg}")
            elif tool == "git_push":
                git_ops.append("  push")

    if not written_files and not terminal_cmds and not git_ops:
        return ""

    sections: list[str] = ["## Dev session changes (this session)"]
    if written_files:
        sections.append("Files changed:")
        sections.extend(written_files[:20])
        if len(written_files) > 20:
            sections.append(f"  ... and {len(written_files) - 20} more")
    if terminal_cmds:
        sections.append("Terminal commands:")
        sections.extend(terminal_cmds[-10:])
    if git_ops:
        sections.append("Git operations:")
        sections.extend(git_ops[-5:])
    return "\n".join(sections)


def should_skip_reanchor_safe(diagnostics: dict[str, Any] | None) -> bool:
    def _run() -> bool:

        return bool(should_skip_post_compact_reanchor(diagnostics))

    result = safe_best_effort(
        _run,
        label="post_compact_cleanup.skip_reanchor",
        default=False,
    )
    return bool(result)
