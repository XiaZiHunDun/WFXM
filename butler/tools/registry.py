"""Butler Tool Registry — manages tool schemas and dispatch.

Sub-modules:
  tool_audit.py       — audit recording, result finalization, observation tracking
  builtin_register.py — wires tool schemas to implementations
  registry_gates.py   — optional permission/hook gates (P0-A safe_best_effort)

Independent from Hermes tool system. Tools register here and
the AgentLoop dispatches through this registry.
"""

from __future__ import annotations

import ast
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from butler.core.best_effort import safe_best_effort
from butler.core.effects import with_retry
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
from butler.tools.registry_invoke_ops import call_tool_with_retry
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


# ─── ToolEntry ────────────────────────────────────────────────────


@dataclass(slots=True)
class ToolEntry:
    """Metadata for a registered tool.

    Attributes:
        name:        Unique tool identifier (e.g. ``read_file``).
        toolset:    Logical grouping (``file``, ``shell``, ``search``, …).
        schema:     JSON-Schema dict describing the tool's parameters.
        handler:    Callable that implements the tool.
        check_fn:   Optional callable returning bool for availability check.
        description: Human-readable description for the LLM.
        max_result_size: Optional cap (chars) on a single tool result.
        dynamic_schema_overrides:
                    Optional callable that returns a dict to *patch* the
                    registered schema at definition-time (e.g. to fill in
                    enum values discovered at runtime).
    """

    name: str
    toolset: str
    schema: dict[str, Any]
    handler: Callable[..., Any]
    check_fn: Callable[..., bool] | None = None
    description: str = ""
    max_result_size: int | None = None
    dynamic_schema_overrides: Callable[..., dict[str, Any]] | None = None


# ─── ToolRegistry ────────────────────────────────────────────────


class ToolRegistry:
    """Central registry for tool schemas, handlers, and availability.

    Thread-safe via ``threading.RLock``.  Provides dictionary-style
    access for backward compatibility (``_REGISTRY``) while also
    exposing a clean class-based API.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._lock = threading.RLock()
        self._check_fn_cache: dict[str, tuple[bool, float]] = {}
        self._check_fn_cache_ttl: float = 30.0

    # ── registration ────────────────────────────────────────────

    def register(
        self,
        tool_name: str,
        schema: dict[str, Any],
        handler: Callable[..., Any],
        check_fn: Callable[..., bool] | None = None,
        toolset: str = "builtin",
        description: str = "",
        max_result_size: int | None = None,
        dynamic_schema_overrides: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        """Register a tool.

        Parameters
        ----------
        tool_name:
            Unique identifier for the tool.
        schema:
            JSON-Schema dict for the tool's parameters.
        handler:
            Callable that implements the tool.
        check_fn:
            Optional callable returning bool; if provided, the tool
            is only reported as *available* when this returns ``True``.
        toolset:
            Logical grouping (``file``, ``shell``, …).
        description:
            Human-readable description sent to the model.
        max_result_size:
            Optional cap on a single tool result (in characters).
        dynamic_schema_overrides:
            Optional callable returning a dict merged into the
            registered schema whenever ``get_definitions`` is called.
        """
        from butler.tools.tool_doc_templates import enrich_tool_description

        with self._lock:
            self._tools[tool_name] = ToolEntry(
                name=tool_name,
                toolset=toolset,
                schema=schema,
                handler=handler,
                check_fn=check_fn,
                description=enrich_tool_description(tool_name, description),
                max_result_size=max_result_size,
                dynamic_schema_overrides=dynamic_schema_overrides,
            )

    # ── definitions ─────────────────────────────────────────────

    def _build_definitions(self) -> list[dict[str, Any]]:
        """Build function-calling definitions from registered tools only.

        Pure method — no MCP extension, no toolset filtering.
        Module-level wrappers add cross-cutting concerns.
        """
        with self._lock:
            result: list[dict[str, Any]] = []
            for entry in self._tools.values():
                schema = entry.schema
                if entry.dynamic_schema_overrides is not None:
                    try:
                        overrides = entry.dynamic_schema_overrides()
                        if overrides:
                            schema = {**schema, **overrides}
                    except Exception:
                        logger.debug(
                            "dynamic_schema_overrides failed for %s", entry.name, exc_info=True
                        )
                result.append({
                    "type": "function",
                    "function": {
                        "name": entry.name,
                        "description": entry.description,
                        "parameters": schema,
                    },
                })
            return result

    def get_definitions(self) -> list[dict[str, Any]]:
        """Return tool schemas in OpenAI function-calling format.

        Override in subclasses to add MCP / filtering.  The default
        implementation returns only registered tools.
        """
        return self._build_definitions()

    def get_definitions_unfiltered(self) -> list[dict[str, Any]]:
        """Return tool definitions without toolset filtering."""
        return self._build_definitions()

    # ── handler / access ─────────────────────────────────────────

    def get_handler(self, tool_name: str) -> Callable[..., Any] | None:
        """Return the handler callable for *tool_name*, or ``None``."""
        with self._lock:
            entry = self._tools.get(tool_name)
            return entry.handler if entry is not None else None

    def is_available(self, tool_name: str) -> bool:
        """Check whether *tool_name* is registered and available.

        If the tool has a ``check_fn``, the result is cached for
        ``check_fn_cache_ttl`` seconds (default 30 s) to avoid
        repeated expensive calls.
        """
        with self._lock:
            entry = self._tools.get(tool_name)
            if entry is None:
                return False
            if entry.check_fn is None:
                return True
            cached = self._check_fn_cache.get(tool_name)
            now = time.monotonic()
            if cached is not None and (now - cached[1]) < self._check_fn_cache_ttl:
                return cached[0]
        try:
            ok = bool(entry.check_fn())
        except Exception:
            logger.debug("check_fn failed for %s", tool_name, exc_info=True)
            ok = False
        with self._lock:
            self._check_fn_cache[tool_name] = (ok, time.monotonic())
        return ok

    def get_max_result_size(self, tool_name: str, default: int | None = None) -> int | None:
        """Return the max result size for *tool_name*, or *default*."""
        with self._lock:
            entry = self._tools.get(tool_name)
            if entry is None:
                return default
            return entry.max_result_size

    # ── mutation ────────────────────────────────────────────────

    def unregister(self, tool_name: str) -> None:
        """Remove *tool_name* from the registry."""
        with self._lock:
            self._tools.pop(tool_name, None)
            self._check_fn_cache.pop(tool_name, None)

    def list_tools(self) -> list[str]:
        """Return a sorted list of all registered tool names."""
        with self._lock:
            return sorted(self._tools.keys())

    def clear(self) -> None:
        """Remove all registered tools and clear the check_fn cache."""
        with self._lock:
            self._tools.clear()
            self._check_fn_cache.clear()

    # ── dict-like access for backward compatibility ──────────────

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def __getitem__(self, tool_name: str) -> ToolEntry:
        return self._tools[tool_name]

    def get(self, tool_name: str, default: Any = None) -> ToolEntry | None:
        return self._tools.get(tool_name, default)

    def items(self) -> Iterable[tuple[str, ToolEntry]]:
        return self._tools.items()

    def values(self) -> Iterable[ToolEntry]:
        return self._tools.values()

    def __len__(self) -> int:
        return len(self._tools)


# ─── Global Singleton ─────────────────────────────────────────────


registry = ToolRegistry()


# ─── Backward-Compatible Module-Level Interface ────────────────────


_REGISTRY: dict[str, ToolEntry] = registry._tools


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
    """Register a tool (backward-compatible wrapper around ``ToolRegistry``)."""
    registry.register(
        tool_name=name,
        schema=schema,
        handler=handler,
        toolset=toolset,
        description=description,
    )


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return OpenAI function-calling format tool definitions."""
    _ensure_builtins()
    raw = registry.get_definitions()
    mcp_available = mcp_tools_enabled()
    if mcp_available:
        raw = extend_mcp_definitions(raw)
    return filter_definitions_by_toolset(raw)


def get_tool_definitions_unfiltered() -> list[dict[str, Any]]:
    """Return tool definitions without ``BUTLER_TOOLSET`` runtime projection."""
    _ensure_builtins()
    raw = registry.get_definitions_unfiltered()
    mcp_available = mcp_tools_enabled()
    if mcp_available:
        raw = extend_mcp_definitions(raw)
    return raw


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

    try:
        result = call_tool_with_retry(name, lambda: dispatch_mcp_tool(name, args))
    except Exception as exc:
        logger.error("MCP tool %s failed: %s", name, exc)
        return _finalize_tool_result(
            name,
            args,
            {"error": f"MCP tool failed: {exc}"},
            started_at=started_at,
        )

    if result is None:
        return _finalize_tool_result(
            name,
            args,
            {"error": f"Unknown MCP tool: {name}"},
            started_at=started_at,
        )
    return apply_post_tool_hooks(
        name,
        args,
        _finalize_tool_result(name, args, result, started_at=started_at),
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
        return blocked

    mcp_result = dispatch_mcp_if_applicable(
        name,
        args,
        dispatch_mcp=_dispatch_mcp_tool,
    )
    if mcp_result is not None:
        return mcp_result

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

        return check_local_project_inventory_tool_block(name)

    inventory_block = safe_best_effort(
        _inventory_run,
        label="registry.local_project_inventory",
        default=None,
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
        return apply_post_tool_hooks(
            name,
            args,
            _finalize_tool_result(name, args, arg_err, started_at=started_at),
            failed=True,
        )

    call_args = inject_read_file_preread(name, call_args)
    return invoke_registered_tool_handler(
        name=name,
        args=args,
        call_args=call_args,
        handler=entry.handler,
        started_at=started_at,
        finalize_result=_finalize_tool_result,
        apply_hooks=apply_post_tool_hooks,
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


# ─── Lazy builtin loading ──────────────────────────────────────────


_builtins_loaded = False


def reset_tool_registry() -> None:
    """Clear in-process tool registry (test isolation / diagnostics)."""
    global _builtins_loaded
    registry.clear()
    _builtins_loaded = False
    _wire_tool_registry_read_port()


def _ensure_builtins() -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    from butler.tools.builtin_register import _register_builtin_tools

    _register_builtin_tools()


# ─── tool_error helper ────────────────────────────────────────────


def tool_error(
    message: str,
    *,
    code: str = "TOOL_ERROR",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standardized error dict for tool responses.

    Parameters
    ----------
    message:
        Human-readable error description.
    code:
        Machine-readable error code (default ``"TOOL_ERROR"``).
    details:
        Optional extra context.

    Returns
    -------
    dict[str, Any]
        Error payload suitable for wrapping in a tool result.
    """
    err: dict[str, Any] = {"error": message, "code": code}
    if details:
        err["details"] = details
    return err


# ─── AST-based tool discovery ─────────────────────────────────────


def discover_builtin_tools(tools_dir: str) -> list[tuple[str, str]]:
    """Scan a directory for ``.py`` files containing top-level
    ``register(...)`` calls, using AST parsing.

    This enables **static** discovery of tools without importing
    the modules (avoiding side-effects and circular imports).

    Parameters
    ----------
    tools_dir:
        Absolute path to the directory to scan.

    Returns
    -------
    list[tuple[str, str]]
        Pairs of ``(tool_name, file_path)`` for every ``register(...)``
        call found at module top-level.
    """
    results: list[tuple[str, str]] = []
    if not os.path.isdir(tools_dir):
        return results

    for fname in sorted(os.listdir(tools_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        fpath = os.path.join(tools_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as fh:
                source = fh.read()
        except (OSError, UnicodeDecodeError):
            continue

        try:
            tree = ast.parse(source, filename=fpath)
        except SyntaxError:
            continue

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.Expr):
                continue
            call = node.value
            if not isinstance(call, ast.Call):
                continue
            # Match: register(...)  or  registry.register(...)
            func = call.func
            is_register_call = False
            if isinstance(func, ast.Name) and func.id == "register":
                is_register_call = True
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "register"
                and isinstance(func.value, ast.Name)
                and func.value.id == "registry"
            ):
                is_register_call = True
            if not is_register_call:
                continue

            # Extract the tool name from the first positional arg or keyword arg
            tool_name: str | None = None
            if call.args:
                first = call.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    tool_name = first.value
            if tool_name is None:
                for kw in call.keywords:
                    if kw.arg in ("name", "tool_name"):
                        val = kw.value
                        if isinstance(val, ast.Constant) and isinstance(val.value, str):
                            tool_name = val.value
                        break
            if tool_name:
                results.append((tool_name, fpath))

    return results


# ─── Backward-compatible re-exports from builtin_impl ──────────────

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