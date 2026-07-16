"""Butler Tool Registry — manages tool schemas and dispatch.

Sub-modules:
  tool_audit.py       — audit recording, result finalization, observation tracking
  builtin_register.py — wires tool schemas to implementations
  registry_gates.py   — optional permission/hook gates (P0-A safe_best_effort)

Independent from Hermes tool system. Tools register here and
the AgentLoop dispatches through this registry.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, cast

from butler.core.best_effort import safe_best_effort
from butler.tools.registry_gates import (
    apply_post_tool_hooks,
    dispatch_mcp_if_applicable,
    extend_mcp_definitions,
    filter_definitions_by_toolset,
    inject_read_file_preread,
    invoke_registered_tool_handler,
    mcp_tools_enabled,
    network_search_gate,
    normalize_and_validate_args,
    permission_denied_hint,
    permission_request_hooks_block,
    plan_mode_mcp_block,
    pre_tool_hooks_block,
    project_permission_block,
    session_read_recall_block,
)
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
        schema: dict[str, Any],
        handler: Callable[..., Any],
        toolset: str = "default",
    ):
        self.name = name
        self.description = description
        self.schema = schema
        self.handler = handler
        self.toolset = toolset


_REGISTRY: dict[str, ToolEntry] = {}


class _LiveToolRegistryRead:
    def is_tool_registered(self, name: str) -> bool:
        return name in _REGISTRY


def _wire_tool_registry_read_port() -> None:
    from butler.contracts.tool_registry_registry import set_tool_registry_read

    set_tool_registry_read(_LiveToolRegistryRead())


_wire_tool_registry_read_port()


def register(
    name: str,
    description: str,
    schema: dict[str, Any],
    handler: Callable[..., Any],
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


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return OpenAI function-calling format tool definitions."""
    _ensure_builtins()
    mcp_available = mcp_tools_enabled()
    result = []
    for entry in _REGISTRY.values():
        if entry.toolset in ("mcp", "mcp_self_service") and not mcp_available:
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
        result = extend_mcp_definitions(result)
    return cast(list[dict[str, Any]], filter_definitions_by_toolset(result))


def get_tool_definitions_unfiltered() -> list[dict[str, Any]]:
    """Return tool definitions without ``BUTLER_TOOLSET`` runtime projection."""
    _ensure_builtins()
    mcp_available = mcp_tools_enabled()
    result: list[dict[str, Any]] = []
    for entry in _REGISTRY.values():
        if entry.toolset in ("mcp", "mcp_self_service") and not mcp_available:
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
        result = extend_mcp_definitions(result)
    return result


def _dispatch_mcp_tool(name: str, args: dict[str, Any]) -> str:
    """Run permission/hooks/audit pipeline for MCP tools."""
    from butler.mcp.registry_hook import dispatch_mcp_tool

    started_at = time.monotonic()
    plan_block = plan_mode_mcp_block(name)
    if plan_block:
        return _permission_denied_tool_result(
            name,
            args,
            plan_block,
            code="PLAN_MODE_BLOCKED",
        )

    perm_block = project_permission_block(name, args)
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

    pre_block = pre_tool_hooks_block(name, args)
    if pre_block:
        return _permission_denied_tool_result(
            name,
            args,
            pre_block,
            code="HOOK_BLOCKED",
            started_at=started_at,
        )

    result = dispatch_mcp_tool(name, args)
    if result is None:
        return cast(
            str,
            _finalize_tool_result(
                name,
                args,
                {"error": f"Unknown MCP tool: {name}"},
                started_at=started_at,
            ),
        )
    return cast(
        str,
        apply_post_tool_hooks(
            name,
            args,
            cast(
                str,
                _finalize_tool_result(name, args, result, started_at=started_at),
            ),
        ),
    )


def dispatch_tool(name: str, args: dict[str, Any]) -> str:
    """Dispatch a tool call by name. Returns result as string."""
    _ensure_builtins()
    started_at = time.monotonic()

    blocked = network_search_gate(
        name,
        args,
        finalize=_finalize_tool_result,
        started_at=started_at,
    )
    if blocked is not None:
        return cast(str, blocked)

    mcp_result = dispatch_mcp_if_applicable(
        name,
        args,
        dispatch_mcp=_dispatch_mcp_tool,
    )
    if mcp_result is not None:
        return cast(str, mcp_result)

    entry = _REGISTRY.get(name)
    if entry is None:
        return cast(
            str,
            _finalize_tool_result(
                name,
                args,
                {"error": f"Unknown tool: {name}"},
                started_at=time.monotonic(),
            ),
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

    recall_block = session_read_recall_block(name)
    if recall_block:
        return _permission_denied_tool_result(
            name,
            args,
            recall_block,
            code="SESSION_READ_RECALL_BLOCKED",
        )

    def _inventory_run() -> str | None:
        from butler.core.session_recall_intent import check_local_project_inventory_tool_block

        return cast(str | None, check_local_project_inventory_tool_block(name))

    inventory_block = cast(
        str | None,
        safe_best_effort(
            _inventory_run,
            label="registry.local_project_inventory",
            default=None,
        ),
    )
    if inventory_block:
        return _permission_denied_tool_result(
            name,
            args,
            inventory_block,
            code="LOCAL_PROJECT_INVENTORY_BLOCKED",
        )

    perm_block = project_permission_block(name, args)
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

    started_at = time.monotonic()
    perm_block = permission_request_hooks_block(name, args)
    if perm_block:
        return _permission_denied_tool_result(
            name,
            args,
            perm_block,
            code="PERMISSION_REQUEST_HOOK",
            started_at=started_at,
        )
    pre_block = pre_tool_hooks_block(name, args)
    if pre_block:
        return _permission_denied_tool_result(
            name,
            args,
            pre_block,
            code="HOOK_BLOCKED",
            started_at=started_at,
        )

    call_args, arg_err = normalize_and_validate_args(name, args)
    if arg_err is not None:
        return cast(
            str,
            apply_post_tool_hooks(
                name,
                args,
                cast(
                    str,
                    _finalize_tool_result(name, args, arg_err, started_at=started_at),
                ),
                failed=True,
            ),
        )

    call_args = inject_read_file_preread(name, call_args)
    return cast(
        str,
        invoke_registered_tool_handler(
            name=name,
            args=args,
            call_args=call_args,
            handler=entry.handler,
            started_at=started_at,
            finalize_result=_finalize_tool_result,
            apply_hooks=apply_post_tool_hooks,
        ),
    )


def _permission_denied_tool_result(
    name: str,
    args: dict[str, Any],
    reason: str,
    *,
    code: str,
    started_at: float | None = None,
) -> str:
    payload: dict[str, Any] = {"error": reason, "code": code}
    hint = permission_denied_hint(name, args, reason)
    if hint:
        payload["permission_denied_hint"] = hint
    return cast(
        str,
        _finalize_tool_result(
            name,
            args,
            payload,
            started_at=started_at if started_at is not None else time.monotonic(),
        ),
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


_builtins_loaded = False


def reset_tool_registry() -> None:
    """Clear in-process tool registry (test isolation / diagnostics)."""
    global _builtins_loaded
    _REGISTRY.clear()
    _builtins_loaded = False
    _wire_tool_registry_read_port()


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
