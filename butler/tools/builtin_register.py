"""Builtin tool registration — wires tool schemas to implementations."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

from butler.tools.registry import register
from butler.tools.builtin_impl import (
    _tool_read_file,
    _tool_write_file,
    _tool_delete_file,
    _tool_patch,
    _tool_terminal,
    _tool_search_files,
    _tool_list_directory,
    _tool_skills_list,
    _tool_skill_view,
    _tool_run_workflow,
    _tool_delegate_task,
)


def _tool_mcp_tool_search(query: str, limit: int = 12, promote: bool = False) -> str:
    from butler.mcp.deferred import tool_search_handler

    return tool_search_handler(query, limit=limit, promote=promote)


def _tool_load_mcp_tools(tool_names: list | None = None) -> str:
    from butler.mcp.deferred import load_mcp_tools_handler

    return load_mcp_tools_handler(list(tool_names or []))


def _tool_ask_clarification(question: str, options: list | None = None) -> str:
    import json

    q = str(question or "").strip()
    if not q:
        return json.dumps({"ok": False, "code": "CLARIFICATION_EMPTY", "error": "question required"})
    opts = [str(o).strip() for o in (options or []) if str(o).strip()]
    return json.dumps(
        {"ok": True, "code": "CLARIFICATION", "question": q, "options": opts},
        ensure_ascii=False,
    )


def _tool_opencode_task(task: str, workspace: str = "", timeout_seconds: int = 0) -> str:
    import json as _json

    from butler.extensions.opencode import get_opencode_bridge

    bridge = get_opencode_bridge()
    if not workspace:
        from butler.tools.safe_root import get_tool_safe_root

        workspace = str(get_tool_safe_root())
    result = bridge.execute_task(
        task,
        workspace=workspace,
        timeout_seconds=timeout_seconds or 600,
    )
    return _json.dumps(result, ensure_ascii=False)


def _register_opencode_tool() -> None:
    register(
        name="opencode_task",
        description=(
            "Delegate a coding task to OpenCode AI agent. "
            "OpenCode can read, edit, grep, run commands, and manage code in a workspace. "
            "Use for complex coding tasks that need multi-step file operations."
        ),
        schema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The coding task description for OpenCode",
                },
                "workspace": {
                    "type": "string",
                    "description": "Workspace directory path (defaults to current project root)",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Max seconds to wait (default 600)",
                    "default": 600,
                },
            },
            "required": ["task"],
        },
        handler=_tool_opencode_task,
        toolset="opencode",
    )


def _register_builtin_tools() -> None:
    """Register Butler's core development tools."""
    from butler.tools.tool_schemas import (
        read_file_schema,
        write_file_schema,
        patch_schema,
        delete_file_schema,
        terminal_schema,
        search_files_schema,
        list_directory_schema,
    )

    register(name="read_file", description="Read content from a file. Returns the file content as text.",
             schema=read_file_schema(), handler=_tool_read_file, toolset="file")
    register(name="write_file", description="Write content to a file. Creates the file if it doesn't exist.",
             schema=write_file_schema(), handler=_tool_write_file, toolset="file")
    register(name="patch", description="Replace a specific string in a file. The old_string must match exactly.",
             schema=patch_schema(), handler=_tool_patch, toolset="file")
    register(name="delete_file", description="Delete a regular file under the project workspace. Prefer this over terminal rm.",
             schema=delete_file_schema(), handler=_tool_delete_file, toolset="file")
    register(name="terminal", description="Execute a restricted argv command when BUTLER_ENABLE_TERMINAL=1.",
             schema=terminal_schema(), handler=_tool_terminal, toolset="shell")
    register(name="search_files", description="Search for a pattern in files using ripgrep.",
             schema=search_files_schema(), handler=_tool_search_files, toolset="search")
    register(name="list_directory", description="List files and directories in a given path.",
             schema=list_directory_schema(), handler=_tool_list_directory, toolset="file")

    # ── delegate_task (Butler-native) ─────────────────────────
    register(
        name="skills_list",
        description="List available skills (metadata only). Use skill_view to load full content.",
        schema={"type": "object", "properties": {}},
        handler=_tool_skills_list,
        toolset="skills",
    )

    register(
        name="skill_view",
        description="Load full content of a skill by name.",
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name (kebab-case)"},
            },
            "required": ["name"],
        },
        handler=_tool_skill_view,
        toolset="skills",
    )

    try:
        from butler.core.harness_flags import (
            ask_clarification_enabled,
            mcp_deferred_tools_enabled,
        )

        if mcp_deferred_tools_enabled():
            register(
                name="mcp_tool_search",
                description=(
                    "Search configured MCP tools by keyword without loading full schemas. "
                    "Use load_mcp_tools to promote names into the active tool set for this session."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "default": 12},
                        "promote": {
                            "type": "boolean",
                            "description": "If true, also promote all matches for this session",
                            "default": False,
                        },
                    },
                    "required": ["query"],
                },
                handler=_tool_mcp_tool_search,
                toolset="mcp",
            )
            register(
                name="load_mcp_tools",
                description="Promote MCP tool registered names so full schemas are available on the next LLM turn.",
                schema={
                    "type": "object",
                    "properties": {
                        "tool_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "MCP registered tool names (mcp_*)",
                        },
                    },
                    "required": ["tool_names"],
                },
                handler=_tool_load_mcp_tools,
                toolset="mcp",
            )
        if ask_clarification_enabled():
            register(
                name="ask_clarification",
                description=(
                    "Ask the user a clarifying question and end the current agent turn. "
                    "Use when requirements are ambiguous before destructive or expensive work."
                ),
                schema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional multiple-choice labels",
                        },
                    },
                    "required": ["question"],
                },
                handler=_tool_ask_clarification,
                toolset="butler",
            )
    except Exception as exc:
        logger.debug("Harness builtin tools skipped: %s", exc)

    from butler.tools.tool_schemas import delegate_task_schema, run_workflow_schema

    register(name="run_workflow",
             description="Run a named project workflow (DAG of dev/content/review agents).",
             schema=run_workflow_schema(), handler=_tool_run_workflow, toolset="delegation")
    register(name="delegate_task",
             description="Delegate a task to a project-level agent (dev/content/review).",
             schema=delegate_task_schema(), handler=_tool_delegate_task, toolset="delegation")

    from butler.tools.registry_tools import register_registry_tools

    register_registry_tools(register)

    from butler.tools.memory_tools import register_memory_tools

    register_memory_tools(register)

    from butler.core.transcript_search import register_transcript_search_tool

    register_transcript_search_tool(register)

    from butler.tools.execute_code import register_execute_code_tool

    register_execute_code_tool(register)

    from butler.tools.workflow_tools import register_workflow_tools

    register_workflow_tools(register)

    from butler.tools.knowledge_search import register_knowledge_tools

    register_knowledge_tools(register)

    from butler.tools.web_fetch import register_web_fetch_tool

    register_web_fetch_tool(register)

    from butler.tools.web_search import register_web_search_tool

    register_web_search_tool(register)

    from butler.tools.git_tools import register_git_tools

    register_git_tools(register)

    from butler.tools.runtime_tools import register_runtime_tools

    register_runtime_tools(register)

    from butler.tools.session_todos_tools import register_session_todos_tools

    register_session_todos_tools(register)

    from butler.tools.delegate_yield_tools import register_delegate_yield_tools

    register_delegate_yield_tools(register)

    from butler.tools.download_tools import register_download_tools

    register_download_tools(register)

    from butler.tools.document_reader import register_document_tools

    register_document_tools(register)

    from butler.tools.data_query import register_data_query_tools

    register_data_query_tools(register)

    from butler.tools.reminder import register_reminder_tools

    register_reminder_tools(register)

    from butler.tools.project_todos import register_project_todos_tools

    register_project_todos_tools(register)

    from butler.tools.mcp_self_service import register_mcp_self_service_tools

    register_mcp_self_service_tools(register)

    from butler.tools.memo import register_memo_tools

    register_memo_tools(register)

    from butler.tools.contacts import register_contact_tools

    register_contact_tools(register)

    from butler.tools.expense import register_expense_tools

    register_expense_tools(register)

    from butler.tools.habits import register_habit_tools

    register_habit_tools(register)

    from butler.tools.multimodal_tools import register_multimodal_tools

    register_multimodal_tools(register)

    from butler.tools.config_tools import register_config_tools

    register_config_tools(register)

    from butler.extensions.opencode import opencode_enabled

    if opencode_enabled():
        _register_opencode_tool()

    try:
        from butler.dev_engine.dev_tools import register_dev_engine_tools

        register_dev_engine_tools(register)
    except Exception as exc:
        logger.debug("Dev engine tools registration skipped: %s", exc)
