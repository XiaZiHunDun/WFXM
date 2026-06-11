"""Butler Tool Registry — manages tool schemas and dispatch.

Sub-modules:
  tool_audit.py       — audit recording, result finalization, observation tracking
  builtin_register.py — wires tool schemas to implementations

Independent from Hermes tool system. Tools register here and
the AgentLoop dispatches through this registry.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List

from butler.tools.tool_audit import (  # noqa: F401
    _finalize_tool_result,
    _maybe_record_tool_observation,
    _parse_json_object,
    _record_tool_audit,
    _TOOL_AUDIT_EVENTS,
    _TOOL_AUDIT_EVENTS_BY_SESSION,
    _TOOL_AUDIT_LOCK,
    _tool_result_code,
    _tool_result_ok,
    finalize_tool_result,
    get_tool_audit_events,
    pop_last_tool_audit_for_tool,
    reset_tool_audit_events,
)

logger = logging.getLogger(__name__)

MAX_READ_FILE_LINES = 1000
MAX_TERMINAL_TIMEOUT_SECONDS = 120


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

    from butler.plan.mode import check_plan_mode_block

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
    try:
        from butler.tools.tool_arg_normalize import normalize_tool_args, validate_tool_args

        call_args = normalize_tool_args(name, call_args)
        arg_err = validate_tool_args(name, call_args)
        if arg_err is not None:
            return _apply_post_tool_hooks(
                name,
                args,
                _finalize_tool_result(name, args, arg_err, started_at=started_at),
                failed=True,
            )
    except Exception as exc:
        logger.debug("tool arg normalize skipped: %s", exc)
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
        except Exception as exc:
            logger.debug("dispatch tool skipped: %s", exc)
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


_builtins_loaded = False


def _ensure_builtins() -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    from butler.tools.builtin_register import _register_builtin_tools

    _register_builtin_tools()


# ── Backward-compatible re-exports from builtin_impl ──────────────

from butler.tools.builtin_impl import (  # noqa: F401, E402
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
