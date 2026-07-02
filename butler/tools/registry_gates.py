"""Optional dispatch gates for ``butler.tools.registry`` (P0-A)."""

from __future__ import annotations

import json
from typing import Any

from butler.core.best_effort import safe_best_effort


def mcp_tools_enabled() -> bool:
    def _run() -> bool:
        from butler.mcp.config import mcp_enabled

        return bool(mcp_enabled())

    result = safe_best_effort(
        _run,
        label="registry.mcp_enabled",
        default=False,
    )
    return bool(result)


def extend_mcp_definitions(definitions: list[dict]) -> list[dict]:
    def _run() -> list[dict]:
        from butler.mcp.registry_hook import get_mcp_tool_definitions

        return [*definitions, *get_mcp_tool_definitions()]

    result = safe_best_effort(
        _run,
        label="registry.mcp_tool_definitions",
        default=None,
    )
    return definitions if result is None else result


def filter_definitions_by_toolset(definitions: list[dict]) -> list[dict]:
    def _run() -> list[dict]:
        from butler.tools.toolset_profiles import filter_definitions_by_toolset

        return filter_definitions_by_toolset(definitions)

    result = safe_best_effort(
        _run,
        label="registry.toolset_filter",
        default=None,
    )
    return definitions if result is None else result


def plan_mode_mcp_block(name: str) -> str | None:
    def _run() -> str | None:
        from butler.mcp.registry_hook import check_plan_mode_mcp_block

        return check_plan_mode_mcp_block(name)

    return safe_best_effort(
        _run,
        label="registry.mcp_plan_mode",
        default=None,
    )


def project_permission_block(name: str, args: dict) -> str | None:
    def _run() -> str | None:
        from butler.permissions import check_project_permission_block

        return check_project_permission_block(name, args)

    return safe_best_effort(
        _run,
        label="registry.project_permission",
        default=None,
    )


def pre_tool_hooks_block(name: str, args: dict) -> str | None:
    def _run() -> str | None:
        from butler.hooks.runner import run_pre_tool_hooks

        return run_pre_tool_hooks(name, args)

    return safe_best_effort(
        _run,
        label="registry.pre_tool_hooks",
        default=None,
    )


def network_search_gate(
    name: str,
    args: dict,
    *,
    finalize,
    started_at: float,
) -> str | None:
    def _run() -> str | None:
        from butler.tools.network_search_policy import (
            check_network_search_tool_block,
            record_network_search_tool,
        )

        block = check_network_search_tool_block(name, args if isinstance(args, dict) else {})
        if block:
            return finalize(name, args, block, started_at=started_at)
        record_network_search_tool(name)
        return None

    return safe_best_effort(
        _run,
        label="registry.network_search_policy",
        default=None,
    )


def dispatch_mcp_if_applicable(name: str, args: dict, *, dispatch_mcp) -> str | None:
    def _run() -> str | None:
        from butler.mcp.registry_hook import is_mcp_tool

        if is_mcp_tool(name):
            return dispatch_mcp(name, args)
        return None

    return safe_best_effort(
        _run,
        label="registry.mcp_dispatch_route",
        default=None,
    )


def session_read_recall_block(name: str) -> str | None:
    def _run() -> str | None:
        from butler.core.session_recall_intent import check_session_read_recall_tool_block

        return check_session_read_recall_tool_block(name)

    return safe_best_effort(
        _run,
        label="registry.session_read_recall",
        default=None,
    )


def permission_request_hooks_block(name: str, args: dict) -> str | None:
    def _run() -> str | None:
        from butler.execution_context import get_current_session_key
        from butler.hooks.runner import run_permission_request_hooks

        sk = str(get_current_session_key() or "").strip()
        return run_permission_request_hooks(name, args, session_key=sk)

    return safe_best_effort(
        _run,
        label="registry.permission_request_hooks",
        default=None,
    )


def normalize_and_validate_args(
    name: str,
    args: dict,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    def _run() -> tuple[dict[str, Any], dict[str, Any] | None]:
        from butler.tools.tool_arg_normalize import normalize_tool_args, validate_tool_args

        call_args = normalize_tool_args(name, dict(args))
        arg_err = validate_tool_args(name, call_args)
        return call_args, arg_err

    result = safe_best_effort(
        _run,
        label="registry.tool_arg_normalize",
        default=None,
    )
    if result is None:
        return dict(args), None
    return result


def inject_read_file_preread(name: str, call_args: dict[str, Any]) -> dict[str, Any]:
    if name != "read_file":
        return call_args

    def _run() -> dict[str, Any]:
        from pathlib import Path

        from butler.core.preread_context import build_preread_block, inject_preread_into_args
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        ws = None
        if orch is not None:
            proj = orch.project_manager.get_current()
            if proj is not None:
                ws = Path(proj.workspace)
        block = build_preread_block(ws, str(call_args.get("path") or ""))
        if block:
            return inject_preread_into_args(call_args, block)
        return call_args

    result = safe_best_effort(
        _run,
        label="registry.read_file_preread",
        default=None,
    )
    return call_args if result is None else result


def note_web_search_outcome(result: Any) -> None:
    safe_best_effort(
        lambda: _note_web_search_outcome(result),
        label="registry.web_search_outcome",
        default=None,
    )


def _note_web_search_outcome(result: Any) -> None:
    from butler.tools.network_search_policy import note_web_search_outcome

    note_web_search_outcome(result)


def permission_denied_hint(name: str, args: dict, reason: str) -> str | None:
    def _run() -> str | None:
        from butler.hooks.runner import run_permission_denied_hooks

        return run_permission_denied_hooks(name, args, reason)

    return safe_best_effort(
        _run,
        label="registry.permission_denied_hooks",
        default=None,
    )


def apply_post_tool_hooks(
    name: str,
    args: dict,
    finalized: str,
    *,
    failed: bool = False,
) -> str:
    hook_failed = failed
    try:
        payload = json.loads(finalized)
        if not hook_failed and isinstance(payload, dict):
            hook_failed = (
                payload.get("ok") is False
                or "error" in payload
                or payload.get("success") is False
            )
    except (TypeError, ValueError, json.JSONDecodeError):
        if not hook_failed:
            hook_failed = '"error"' in finalized

    def _run() -> str:
        from butler.hooks.runner import run_post_tool_hooks

        return run_post_tool_hooks(name, args, finalized, failed=hook_failed)

    result = safe_best_effort(
        _run,
        label="registry.post_tool_hooks",
        default=None,
    )
    return finalized if result is None else result


def invoke_registered_tool_handler(
    *,
    name: str,
    args: dict,
    call_args: dict,
    handler: Any,
    started_at: float,
    finalize_result: Any,
    apply_hooks: Any,
) -> str:
    from butler.tools.registry_invoke_ops import invoke_registered_tool_handler as _invoke

    return _invoke(
        name=name,
        args=args,
        call_args=call_args,
        handler=handler,
        started_at=started_at,
        finalize_result=finalize_result,
        apply_hooks=apply_hooks,
    )


def tool_error_payload(name: str, exc: BaseException) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.core.tool_error_policy import apply_tool_error_policy

        raw = apply_tool_error_policy(
            "",
            tool_name=name,
            exc=exc,
        )
        if raw.strip().startswith("{"):
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        return {"error": raw}

    result = safe_best_effort(
        _run,
        label="registry.tool_error_policy",
        default=None,
    )
    if isinstance(result, dict):
        return result
    return {"error": f"Tool '{name}' failed: {exc}"}


__all__ = [
    "apply_post_tool_hooks",
    "dispatch_mcp_if_applicable",
    "extend_mcp_definitions",
    "filter_definitions_by_toolset",
    "inject_read_file_preread",
    "invoke_registered_tool_handler",
    "mcp_tools_enabled",
    "network_search_gate",
    "normalize_and_validate_args",
    "note_web_search_outcome",
    "permission_denied_hint",
    "permission_request_hooks_block",
    "plan_mode_mcp_block",
    "pre_tool_hooks_block",
    "project_permission_block",
    "session_read_recall_block",
    "tool_error_payload",
]
