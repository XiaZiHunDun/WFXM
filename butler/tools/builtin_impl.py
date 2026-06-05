"""Built-in tool implementations — thin facade re-exporting from sub-modules.

Sub-modules:
  file_io.py        — read / write / delete / patch
  terminal_impl.py  — terminal, search, list_directory
  delegate_impl.py  — delegate_task and helpers
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.tools.delegate_impl import (  # noqa: F401
    _delegate_role_label,
    _delegate_task_succeeded,
    _extract_changes_from_messages,
    _extract_issues_from_messages,
    _finalize_delegate_failure,
    _inject_project_agent_skills,
    _orchestrator_for_tool,
    _project_agent_raw_message,
    _run_subagent_stop_hooks,
    _safe_dispatch,
    _tool_delegate_task,
)
from butler.tools.file_io import (  # noqa: F401
    MAX_READ_FILE_BYTES,
    MAX_READ_FILE_LINES,
    _atomic_write_text,
    _format_open_error,
    _raw_tool_path,
    _read_limited_fd,
    _read_regular_file_bytes,
    _symlink_component_error,
    _tool_delete_file,
    _tool_patch,
    _tool_read_file,
    _tool_write_file,
    _validate_existing_target_unchanged,
    _validate_regular_file_stat,
    _write_all_fd,
)
from butler.tools.terminal_impl import (  # noqa: F401
    MAX_TERMINAL_OUTPUT_CHARS,
    MAX_TERMINAL_TIMEOUT_SECONDS,
    _close_pipe,
    _communicate_limited,
    _is_selectable_pipe,
    _tool_list_directory,
    _tool_search_files,
    _tool_terminal,
)

logger = logging.getLogger(__name__)

# ── Skill / Workflow tools (kept inline — small, few dependencies) ──


def _tool_skills_list(**_) -> str:
    try:
        orch = _orchestrator_for_tool(channel="tool")
        mgr = orch._skill_manager
        if mgr is None:
            return json.dumps({"skills": []})
        skills = [
            {"name": s.get("name"), "description": s.get("description", "")[:200]}
            for s in mgr.list_skills()
        ]
        return json.dumps({"skills": skills}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_skill_view(name: str, **_) -> str:
    try:
        orch = _orchestrator_for_tool(channel="tool")
        mgr = orch._skill_manager
        if mgr is None:
            return json.dumps({"error": "Skill manager unavailable"})
        skill = mgr.get_skill(name)
        if not skill:
            return json.dumps({"error": f"Skill not found: {name}"})
        return json.dumps({
            "name": skill.get("name"),
            "description": skill.get("description"),
            "content": skill.get("content", ""),
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_run_workflow(name: str, hint: str = "", **_) -> str:
    """Execute a project workflow DAG via TaskOrchestrator."""
    # R1-10: route bridge + completion-push lookups through the
    # ``butler.execution_context`` seam so tools → gateway stays a
    # one-way dependency.
    from butler.execution_context import (
        get_current_session_key,
        get_current_turn_bridge,
        try_push_current_turn_workflow_failure,
    )

    bridge = get_current_turn_bridge()
    session_key = ""
    try:
        from butler.workflows.runner import run_workflow_for_project

        if bridge is not None:
            bridge.notify_workflow_step(name, "start", step_index=0, step_total=0)

        orch = _orchestrator_for_tool(channel="cli")
        project = orch.project_manager.get_current()
        if project is None:
            return json.dumps({"error": "No active project; switch project first"}, ensure_ascii=False)
        session_key = str(get_current_session_key() or "").strip()
        text = run_workflow_for_project(
            project,
            name,
            user_hint=hint or "",
            session_key=session_key,
            orchestrator=orch,
        )
        if bridge is not None:
            from butler.report import get_last_report

            report = get_last_report(session_key)
            if report is not None:
                bridge.notify_workflow_finished(report)
        return json.dumps({"success": True, "summary": text}, ensure_ascii=False)
    except Exception as exc:
        try:
            try_push_current_turn_workflow_failure(
                name,
                exc,
                session_key=session_key or str(get_current_session_key() or ""),
            )
        except Exception as push_exc:
            logger.debug("Workflow failure completion push skipped: %s", push_exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
