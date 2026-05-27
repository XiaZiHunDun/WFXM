"""Butler Tool Registry — manages tool schemas and dispatch.

Independent from Hermes tool system. Tools register here and
the AgentLoop dispatches through this registry.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# Schema-referenced limits — canonical definitions live in builtin_impl.py
MAX_READ_FILE_LINES = 1000
MAX_TERMINAL_TIMEOUT_SECONDS = 120
_TOOL_AUDIT_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)
_TOOL_AUDIT_EVENTS_BY_SESSION: dict[str, deque[dict[str, Any]]] = {}
_TOOL_AUDIT_LOCK = threading.RLock()


class ToolEntry:
    __slots__ = ("name", "description", "schema", "handler", "toolset")

    def __init__(
        self,
        name: str,
        description: str,
        schema: dict,
        handler: Callable,
        toolset: str = "default",
    ):
        self.name = name
        self.description = description
        self.schema = schema
        self.handler = handler
        self.toolset = toolset


_REGISTRY: Dict[str, ToolEntry] = {}


def register(
    name: str,
    description: str,
    schema: dict,
    handler: Callable,
    toolset: str = "default",
) -> None:
    from butler.tools.tool_doc_templates import enrich_tool_description

    _REGISTRY[name] = ToolEntry(
        name,
        enrich_tool_description(name, description),
        schema,
        handler,
        toolset,
    )


def get_tool_definitions() -> List[dict]:
    """Return OpenAI function-calling format tool definitions."""
    _ensure_builtins()
    mcp_available = False
    try:
        from butler.mcp.config import mcp_enabled

        mcp_available = bool(mcp_enabled())
    except Exception:
        mcp_available = False
    result = []
    for entry in _REGISTRY.values():
        if entry.toolset == "mcp" and not mcp_available:
            continue
        result.append({
            "type": "function",
            "function": {
                "name": entry.name,
                "description": entry.description,
                "parameters": entry.schema,
            },
        })
    if mcp_available:
        try:
            from butler.mcp.registry_hook import get_mcp_tool_definitions

            result.extend(get_mcp_tool_definitions())
        except Exception as exc:
            logger.debug("MCP tool definitions skipped: %s", exc)
    return result


def _dispatch_mcp_tool(name: str, args: dict) -> str:
    """Run permission/hooks/audit pipeline for MCP tools."""
    from butler.mcp.registry_hook import dispatch_mcp_tool

    started_at = time.monotonic()
    plan_block = None
    try:
        from butler.mcp.registry_hook import check_plan_mode_mcp_block

        plan_block = check_plan_mode_mcp_block(name)
    except Exception as exc:
        logger.debug("MCP plan mode check skipped: %s", exc)
    if plan_block:
        return _permission_denied_tool_result(
            name,
            args,
            plan_block,
            code="PLAN_MODE_BLOCKED",
        )

    try:
        from butler.permissions import check_project_permission_block

        perm_block = check_project_permission_block(name, args)
        if perm_block:
            return _permission_denied_tool_result(
                name,
                args,
                perm_block,
                code=_permission_denied_code(
                    perm_block,
                    default="PERMISSION_RULE_DENIED",
                ),
            )
    except Exception as exc:
        logger.debug("MCP permission rules skipped: %s", exc)

    try:
        from butler.hooks.runner import run_pre_tool_hooks

        pre_block = run_pre_tool_hooks(name, args)
        if pre_block:
            return _permission_denied_tool_result(
                name,
                args,
                pre_block,
                code="HOOK_BLOCKED",
                started_at=started_at,
            )
    except Exception as exc:
        logger.debug("MCP pre tool hooks skipped: %s", exc)

    result = dispatch_mcp_tool(name, args)
    if result is None:
        return _finalize_tool_result(
            name,
            args,
            {"error": f"Unknown MCP tool: {name}"},
            started_at=started_at,
        )
    return _apply_post_tool_hooks(
        name,
        args,
        _finalize_tool_result(name, args, result, started_at=started_at),
    )


def dispatch_tool(name: str, args: dict) -> str:
    """Dispatch a tool call by name. Returns result as string."""
    _ensure_builtins()
    try:
        from butler.mcp.registry_hook import is_mcp_tool

        if is_mcp_tool(name):
            return _dispatch_mcp_tool(name, args)
    except Exception as exc:
        logger.debug("MCP dispatch routing skipped: %s", exc)

    entry = _REGISTRY.get(name)
    if entry is None:
        return _finalize_tool_result(
            name,
            args,
            {"error": f"Unknown tool: {name}"},
            started_at=time.monotonic(),
        )

    from butler.plan_mode import check_plan_mode_block

    plan_block = check_plan_mode_block(name, args)
    if plan_block:
        return _permission_denied_tool_result(
            name,
            args,
            plan_block,
            code="PLAN_MODE_BLOCKED",
        )

    try:
        from butler.permissions import check_project_permission_block

        perm_block = check_project_permission_block(name, args)
        if perm_block:
            return _permission_denied_tool_result(
                name,
                args,
                perm_block,
                code=_permission_denied_code(
                    perm_block,
                    default="PERMISSION_RULE_DENIED",
                ),
            )
    except Exception as exc:
        logger.debug("Project permission rules skipped: %s", exc)

    started_at = time.monotonic()
    try:
        from butler.execution_context import get_current_session_key
        from butler.hooks.runner import run_permission_request_hooks, run_pre_tool_hooks

        sk = str(get_current_session_key() or "").strip()
        perm_block = run_permission_request_hooks(name, args, session_key=sk)
        if perm_block:
            return _permission_denied_tool_result(
                name,
                args,
                perm_block,
                code="PERMISSION_REQUEST_HOOK",
                started_at=started_at,
            )
        pre_block = run_pre_tool_hooks(name, args)
        if pre_block:
            return _permission_denied_tool_result(
                name,
                args,
                pre_block,
                code="HOOK_BLOCKED",
                started_at=started_at,
            )
    except Exception as exc:
        logger.debug("Pre tool hooks skipped: %s", exc)

    call_args = dict(args)
    if name == "read_file":
        try:
            from butler.core.preread_context import build_preread_block, inject_preread_into_args
            from butler.execution_context import get_current_orchestrator

            orch = get_current_orchestrator()
            ws = None
            if orch is not None:
                proj = orch.project_manager.get_current()
                if proj is not None:
                    from pathlib import Path

                    ws = Path(proj.workspace)
            block = build_preread_block(ws, str(call_args.get("path") or ""))
            if block:
                call_args = inject_preread_into_args(call_args, block)
        except Exception:
            pass

    try:
        from butler.tools.tool_implicit_context import merge_implicit_tool_args

        call_args = merge_implicit_tool_args(call_args)
        result = entry.handler(**call_args)
        return _apply_post_tool_hooks(
            name,
            args,
            _finalize_tool_result(name, args, result, started_at=started_at),
        )
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        try:
            from butler.core.tool_error_policy import apply_tool_error_policy

            raw = apply_tool_error_policy(
                "",
                tool_name=name,
                exc=exc,
            )
            payload = json.loads(raw) if raw.strip().startswith("{") else {"error": raw}
        except Exception:
            payload = {"error": f"Tool '{name}' failed: {exc}"}
        err_result = _finalize_tool_result(
            name,
            args,
            payload,
            started_at=started_at,
        )
        return _apply_post_tool_hooks(name, args, err_result, failed=True)


def _permission_denied_tool_result(
    name: str,
    args: dict,
    reason: str,
    *,
    code: str,
    started_at: float | None = None,
) -> str:
    payload: dict[str, Any] = {"error": reason, "code": code}
    try:
        from butler.hooks.runner import run_permission_denied_hooks

        hint = run_permission_denied_hooks(name, args, reason)
        if hint:
            payload["permission_denied_hint"] = hint
    except Exception as exc:
        logger.debug("PermissionDenied hooks skipped: %s", exc)
    return _finalize_tool_result(
        name,
        args,
        payload,
        started_at=started_at if started_at is not None else time.monotonic(),
    )


def _permission_denied_code(reason: str, *, default: str) -> str:
    lowered = str(reason or "").lower()
    if (
        "access denied" in lowered
        or "outside workspace" in lowered
        or "路径在工作区外" in str(reason or "")
        or "sensitive" in lowered
        or "symlink" in lowered
        or "hardlinked" in lowered
    ):
        return "TOOL_SECURITY_DENIED"
    return default


def _apply_post_tool_hooks(
    name: str,
    args: dict,
    finalized: str,
    *,
    failed: bool = False,
) -> str:
    try:
        payload = json.loads(finalized)
        if not failed and isinstance(payload, dict):
            failed = (
                payload.get("ok") is False
                or "error" in payload
                or payload.get("success") is False
            )
    except (TypeError, ValueError, json.JSONDecodeError):
        if not failed:
            failed = '"error"' in finalized
    try:
        from butler.hooks.runner import run_post_tool_hooks

        return run_post_tool_hooks(name, args, finalized, failed=failed)
    except Exception as exc:
        logger.debug("Post tool hooks skipped: %s", exc)
        return finalized


def finalize_tool_result(
    name: str,
    args: dict,
    result: Any,
    *,
    started_at: float | None = None,
) -> str:
    """Apply Butler's tool result envelope and audit record to fallback paths."""
    return _finalize_tool_result(
        name,
        args,
        result,
        started_at=started_at if started_at is not None else time.monotonic(),
    )


def get_tool_audit_events(
    limit: int | None = None,
    *,
    session_key: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent tool audit events with redacted arguments."""
    with _TOOL_AUDIT_LOCK:
        if session_key is None:
            events = list(_TOOL_AUDIT_EVENTS)
        else:
            events = list(_TOOL_AUDIT_EVENTS_BY_SESSION.get(session_key, ()))
    if limit is not None:
        events = events[-max(0, int(limit)):]
    return [dict(event) for event in events]


def reset_tool_audit_events(session_key: str | None = None) -> None:
    """Clear in-memory tool audit events. Intended for tests and diagnostics reset."""
    with _TOOL_AUDIT_LOCK:
        if session_key is None:
            _TOOL_AUDIT_EVENTS.clear()
            _TOOL_AUDIT_EVENTS_BY_SESSION.clear()
            return
        _TOOL_AUDIT_EVENTS_BY_SESSION.pop(session_key, None)
        retained = [
            event for event in _TOOL_AUDIT_EVENTS
            if event.get("session_key") != session_key
        ]
        _TOOL_AUDIT_EVENTS.clear()
        _TOOL_AUDIT_EVENTS.extend(retained[-_TOOL_AUDIT_EVENTS.maxlen:])


def pop_last_tool_audit_for_tool(name: str) -> None:
    """Remove the latest audit event for a tool when replacing it with guardrail halt."""
    with _TOOL_AUDIT_LOCK:
        if not _TOOL_AUDIT_EVENTS or _TOOL_AUDIT_EVENTS[-1].get("tool") != name:
            return
        last = _TOOL_AUDIT_EVENTS.pop()
        session_key = str(last.get("session_key") or "")
        bucket = _TOOL_AUDIT_EVENTS_BY_SESSION.get(session_key)
        if bucket and bucket[-1].get("tool") == name:
            bucket.pop()


def _maybe_record_tool_observation(
    name: str,
    args: dict,
    payload: dict[str, Any],
) -> None:
    try:
        from butler.execution_context import get_current_session_key
        from butler.core.session_transcript import record_tool_observation

        sk = str(get_current_session_key() or "").strip()
        if not sk:
            return
        preview = ""
        if payload.get("error"):
            preview = str(payload.get("error") or "")[:200]
        elif payload.get("mode") == "summary":
            preview = f"summary lines={payload.get('total_lines', '?')}"
        elif payload.get("preview"):
            preview = str(payload.get("preview") or "")[:200]
        else:
            for key in ("content", "result", "output", "message"):
                if payload.get(key):
                    preview = str(payload[key])[:200]
                    break
        if not preview and name == "read_file":
            preview = str(args.get("path") or "")[:120]
        record_tool_observation(
            sk,
            tool=name,
            ok=_tool_result_ok(payload),
            preview=preview,
        )
        try:
            from butler.memory.observer_queue import enqueue_tool_observation
            from butler.execution_context import get_current_orchestrator

            path_hint = str(args.get("path") or args.get("file") or "")
            workspace = None
            orch = get_current_orchestrator()
            if orch is not None:
                try:
                    proj = orch.project_manager.get_current(session_key=sk)
                    if proj is not None:
                        from pathlib import Path

                        workspace = Path(proj.workspace)
                except Exception:
                    workspace = None
            enqueue_tool_observation(
                session_key=sk,
                tool=name,
                ok=_tool_result_ok(payload),
                preview=preview,
                path=path_hint,
                workspace=workspace,
            )
        except Exception:
            pass
    except Exception:
        pass


def _finalize_tool_result(
    name: str,
    args: dict,
    result: Any,
    *,
    started_at: float,
) -> str:
    if isinstance(result, str):
        payload = _parse_json_object(result)
        if payload is None:
            ok = True
            code = "TOOL_OK"
            _record_tool_audit(name, args, ok=ok, code=code, started_at=started_at)
            parsed = _parse_json_object(result)
            if isinstance(parsed, dict):
                _maybe_record_tool_observation(name, args, parsed)
            elif name:
                _maybe_record_tool_observation(
                    name,
                    args,
                    {"preview": str(result)[:200]},
                )
            return result
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        payload = result

    if isinstance(payload, dict):
        ok = _tool_result_ok(payload)
        code = _tool_result_code(name, payload, ok=ok)
        if not ok:
            payload.setdefault("ok", False)
            payload.setdefault("tool", name)
            payload.setdefault("code", code)
            err = str(payload.get("error") or "")
            if err.startswith("Access denied"):
                try:
                    from butler.hooks.runner import run_permission_denied_hooks

                    hint = run_permission_denied_hooks(name, args, err)
                    if hint:
                        payload["permission_denied_hint"] = hint
                except Exception as exc:
                    logger.debug("PermissionDenied hooks skipped: %s", exc)
        _record_tool_audit(name, args, ok=ok, code=code, started_at=started_at)
        _maybe_record_tool_observation(name, args, payload)
        return json.dumps(payload, ensure_ascii=False, default=str)

    _record_tool_audit(name, args, ok=True, code="TOOL_OK", started_at=started_at)
    if isinstance(payload, dict):
        _maybe_record_tool_observation(name, args, payload)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _tool_result_ok(payload: dict[str, Any]) -> bool:
    if payload.get("ok") is False:
        return False
    if "error" in payload:
        return False
    if payload.get("success") is False:
        return False
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return False
    return True


def _tool_result_code(name: str, payload: dict[str, Any], *, ok: bool) -> str:
    if ok:
        return "TOOL_OK"
    guardrail = payload.get("guardrail")
    if isinstance(guardrail, dict):
        action = guardrail.get("action")
        if action == "halt":
            return "TOOL_GUARDRAIL_HALT"
        if action == "block":
            return "TOOL_GUARDRAIL_BLOCKED"
    if payload.get("code"):
        return str(payload["code"])
    error = str(payload.get("error") or "")
    if error == "interrupted":
        return "TOOL_INTERRUPTED"
    if isinstance(payload.get("exit_code"), int) and payload["exit_code"] != 0:
        return "TOOL_EXIT_NONZERO"
    if name not in _REGISTRY:
        return "TOOL_NOT_FOUND"
    lowered = error.lower()
    if (
        "access denied" in lowered
        or "outside workspace" in lowered
        or "路径在工作区外" in error
        or "sensitive" in lowered
        or "symlink" in lowered
        or "hardlinked" in lowered
    ):
        return "TOOL_SECURITY_DENIED"
    if lowered.startswith("file not found") or lowered.startswith("unknown tool"):
        return "TOOL_NOT_FOUND"
    if "timeout" in lowered or "timed out" in lowered:
        return "TOOL_TIMEOUT"
    if "too large" in lowered or "limit" in lowered:
        return "TOOL_RESOURCE_LIMIT"
    return "TOOL_ERROR"


def _record_tool_audit(
    name: str,
    args: dict,
    *,
    ok: bool,
    code: str,
    started_at: float,
) -> None:
    try:
        from butler.execution_context import get_audit_session_key

        session_key = get_audit_session_key()
    except Exception:
        session_key = "unscoped"
    event = {
        "tool": name,
        "ok": ok,
        "code": code,
        "session_key": session_key or "",
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        "arg_keys": sorted(str(key) for key in (args or {}).keys()),
    }
    with _TOOL_AUDIT_LOCK:
        _TOOL_AUDIT_EVENTS.append(event)
        bucket = _TOOL_AUDIT_EVENTS_BY_SESSION.setdefault(
            event["session_key"],
            deque(maxlen=200),
        )
        bucket.append(event)

    try:
        from butler.tools.audit_persist import persist_tool_audit_event

        persist_tool_audit_event(event)
    except Exception as exc:
        logger.debug("Tool audit persist skipped: %s", exc)


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


_builtins_loaded = False


def _ensure_builtins() -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    _register_builtin_tools()


def _register_builtin_tools() -> None:
    """Register Butler's core development tools."""

    # ── read_file ─────────────────────────────────────────────
    register(
        name="read_file",
        description="Read content from a file. Returns the file content as text.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path"},
                "offset": {"type": "integer", "description": "Line number to start from (1-indexed)", "default": 1},
                "limit": {
                    "type": "integer",
                    "description": f"Max lines to read (1-{MAX_READ_FILE_LINES})",
                    "default": 500,
                    "minimum": 1,
                    "maximum": MAX_READ_FILE_LINES,
                },
            },
            "required": ["path"],
        },
        handler=_tool_read_file,
        toolset="file",
    )

    # ── write_file ────────────────────────────────────────────
    register(
        name="write_file",
        description="Write content to a file. Creates the file if it doesn't exist.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        handler=_tool_write_file,
        toolset="file",
    )

    # ── patch ─────────────────────────────────────────────────
    register(
        name="patch",
        description="Replace a specific string in a file. The old_string must match exactly.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "old_string": {"type": "string", "description": "Exact text to find"},
                "new_string": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        handler=_tool_patch,
        toolset="file",
    )

    register(
        name="delete_file",
        description=(
            "Delete a regular file under the project workspace. "
            "Prefer this over terminal rm. Does not remove directories."
        ),
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to delete"},
            },
            "required": ["path"],
        },
        handler=_tool_delete_file,
        toolset="file",
    )

    # ── terminal ──────────────────────────────────────────────
    register(
        name="terminal",
        description="Execute a restricted argv command when BUTLER_ENABLE_TERMINAL=1.",
        schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": f"Timeout in seconds (1-{MAX_TERMINAL_TIMEOUT_SECONDS})",
                    "default": 30,
                    "minimum": 1,
                    "maximum": MAX_TERMINAL_TIMEOUT_SECONDS,
                },
                "workdir": {"type": "string", "description": "Working directory"},
            },
            "required": ["command"],
        },
        handler=_tool_terminal,
        toolset="shell",
    )

    # ── search_files ──────────────────────────────────────────
    register(
        name="search_files",
        description="Search for a pattern in files using ripgrep.",
        schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex)"},
                "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
                "include": {"type": "string", "description": "Glob pattern to filter files"},
            },
            "required": ["pattern"],
        },
        handler=_tool_search_files,
        toolset="search",
    )

    # ── list_directory ────────────────────────────────────────
    register(
        name="list_directory",
        description="List files and directories in a given path.",
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
            },
        },
        handler=_tool_list_directory,
        toolset="file",
    )

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

    register(
        name="run_workflow",
        description=(
            "Run a named project workflow (DAG of dev/content/review agents). "
            "Workflows are declared in project.yaml or .butler/workflows/."
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workflow name (e.g. novel-factory)"},
                "hint": {
                    "type": "string",
                    "description": "Optional user goal appended to each step",
                    "default": "",
                },
            },
            "required": ["name"],
        },
        handler=_tool_run_workflow,
        toolset="delegation",
    )

    register(
        name="delegate_task",
        description="Delegate a task to a project-level agent (dev/content/review). Butler orchestrates the sub-agent.",
        schema={
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "Agent role: 'dev', 'content', or 'review'",
                    "enum": ["dev", "content", "review"],
                },
                "category": {
                    "type": "string",
                    "description": "Optional preset: quick, deep, ultrabrain, ui-build (see delegate_categories.yaml)",
                },
                "task": {"type": "string", "description": "Task description"},
                "context": {"type": "string", "description": "Additional context for the agent"},
            },
            "required": ["role", "task"],
        },
        handler=_tool_delegate_task,
        toolset="delegation",
    )

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



# Tool implementations live in builtin_impl.py
from butler.tools.builtin_impl import (  # noqa: F401
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
    _orchestrator_for_tool,
    _finalize_delegate_failure,
    _run_subagent_stop_hooks,
    _communicate_limited,
    _extract_changes_from_messages,
    _extract_issues_from_messages,
    _delegate_task_succeeded,
    _delegate_role_label,
    _safe_dispatch,
    _project_agent_raw_message,
    _inject_project_agent_skills,
)
