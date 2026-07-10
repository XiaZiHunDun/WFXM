"""Current Butler execution context shared across tool and delegate paths.

R1-10 [H] layering_violation: this module also exposes the
``is_current_turn_owner`` / ``get_current_turn_bridge`` /
``try_push_current_turn_workflow_failure`` / ``owner_required_message``
helpers — the seam that lets ``butler/tools/`` avoid importing from
``butler.gateway.owner_gate``, ``butler.gateway.outbound_bridge`` and
``butler.gateway.completion_notify``. The seam mirrors the R1-3
``EventsSink`` / R1-9 ``MetricsSink`` Protocol pattern but stays
lightweight (thin shims over the gateway module + duck-typed
orchestrator hook for future per-orchestrator policy).

The owner / bridge lookups follow the same precedence:

  1. If an orchestrator is bound via :func:`use_execution_context` and
     that orchestrator exposes a matching duck-typed method /
     attribute (``is_owner(...)`` / ``gateway_bridge``), use it.
  2. Otherwise, fall back to the canonical gateway module
     (back-compat path; behaviour unchanged).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Iterator, cast
from butler.contracts.gateway_registry import get_bridge_access, get_owner_gate

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


_current_orchestrator: ContextVar["ButlerOrchestrator | None"] = ContextVar(
    "butler_current_orchestrator",
    default=None,
)
_current_session_key: ContextVar[str] = ContextVar(
    "butler_current_session_key",
    default="",
)
_current_workflow_step: ContextVar[str] = ContextVar(
    "butler_current_workflow_step",
    default="",
)
_workflow_var_pool: ContextVar[object | None] = ContextVar(
    "butler_workflow_var_pool",
    default=None,
)
_current_loop_role: ContextVar[str] = ContextVar(
    "butler_current_loop_role",
    default="",
)


def get_current_loop_role() -> str:
    """Gateway/subagent loop role: ``butler`` | ``lead`` | ``plan`` | ``dev`` | …"""
    return str(_current_loop_role.get() or "").strip().lower()


def get_current_orchestrator() -> "ButlerOrchestrator | None":
    """Return the orchestrator bound to the current AgentLoop/tool turn."""
    return _current_orchestrator.get()


def get_current_session_key() -> str:
    """Return the external session key bound to the current turn, if any."""
    return _current_session_key.get()


def get_current_workflow_step() -> str:
    """Active workflow step id during DAG node execution (for step-level permissions)."""
    return str(_current_workflow_step.get() or "").strip()


def get_workflow_var_pool() -> object | None:
    return _workflow_var_pool.get()


@contextmanager
def use_workflow_var_pool(pool: object | None) -> Iterator[None]:
    token = _workflow_var_pool.set(pool)
    try:
        yield
    finally:
        _workflow_var_pool.reset(token)


@contextmanager
def use_workflow_step(step_id: str) -> Iterator[None]:
    """Bind workflow step id for tool permission checks in orchestrator nodes."""
    token = _current_workflow_step.set(str(step_id or "").strip())
    try:
        yield
    finally:
        _current_workflow_step.reset(token)


_session_read_recall_gate: ContextVar[bool] = ContextVar(
    "butler_session_read_recall_gate",
    default=False,
)
_local_project_inventory_gate: ContextVar[bool] = ContextVar(
    "butler_local_project_inventory_gate",
    default=False,
)


def is_session_read_recall_gate_active() -> bool:
    return bool(_session_read_recall_gate.get())


@contextmanager
def use_session_read_recall_gate(active: bool = True) -> Iterator[None]:
    token = _session_read_recall_gate.set(bool(active))
    try:
        yield
    finally:
        _session_read_recall_gate.reset(token)


def is_local_project_inventory_gate_active() -> bool:
    return bool(_local_project_inventory_gate.get())


@contextmanager
def use_local_project_inventory_gate(active: bool = True) -> Iterator[None]:
    token = _local_project_inventory_gate.set(bool(active))
    try:
        yield
    finally:
        _local_project_inventory_gate.reset(token)


@contextmanager
def use_loop_role(role: str) -> Iterator[None]:
    token = _current_loop_role.set(str(role or "").strip().lower())
    try:
        yield
    finally:
        _current_loop_role.reset(token)


@contextmanager
def use_execution_context(
    orchestrator: "ButlerOrchestrator | None" = None,
    *,
    session_key: str = "",
    loop_role: str = "",
) -> Iterator[None]:
    """Temporarily bind orchestrator and/or session key for nested tools and delegates."""
    orch_token = None
    role_token = None
    if orchestrator is not None:
        orch_token = _current_orchestrator.set(orchestrator)
    session_token = _current_session_key.set(session_key)
    if loop_role:
        role_token = _current_loop_role.set(str(loop_role).strip().lower())
    try:
        yield
    finally:
        if role_token is not None:
            _current_loop_role.reset(role_token)
        _current_session_key.reset(session_token)
        if orch_token is not None:
            _current_orchestrator.reset(orch_token)


def get_audit_session_key(*, fallback: str = "unscoped") -> str:
    """Session key for tool audit when no external session is bound."""
    key = str(get_current_session_key() or "").strip()
    if key:
        return key
    if get_current_orchestrator() is not None:
        return ""
    return fallback


# ── R1-10 layering seam: owner / bridge / completion helpers ─────────────
#
# Tools call these helpers instead of importing from ``butler.gateway.*``
# directly. The helpers own the duck-typed orchestrator hook + the
# back-compat gateway fallback in one place.
#
# The orchestrator hook is ``__dict__``-checked (not bare ``getattr``)
# so :class:`unittest.mock.MagicMock` orchestrators in unit tests fall
# through to the gateway back-compat path. Real orchestrators that want
# to override must set the attribute explicitly on ``self``.


def _orchestrator_explicit_attr(orch: object, name: str) -> object | None:
    """Return ``orch.<name>`` only if the attribute is set on the instance.

    Mock objects (and ``MagicMock``) auto-create attribute access; a
    bare ``getattr(orch, name, None)`` would always return a child mock
    and break tests that pass a ``MagicMock`` orchestrator. Checking
    ``__dict__`` confines the duck-typed hook to real, explicit
    overrides.
    """
    if orch is None:
        return None
    cls_attrs = getattr(type(orch), "__dict__", {})
    if name in cls_attrs and not isinstance(getattr(type(orch), name, None), property):
        # Class-level attribute (e.g. method) — treat as explicit.
        return getattr(orch, name, None)
    instance_dict = getattr(orch, "__dict__", None)
    if isinstance(instance_dict, dict) and name in instance_dict:
        return cast(object | None, instance_dict[name])
    return None


def is_current_turn_owner(
    *,
    platform: str,
    external_id: str | None = None,
    session_key: str = "",
) -> bool:
    """Layering seam (R1-10) — owner check for the current turn.

    Precedence:

      1. If an orchestrator is bound and exposes a callable ``is_owner``
         attribute with the same keyword signature, use it. This is the
         duck-typed hook for per-orchestrator / per-tenant policy.
      2. Otherwise, fall back to ``butler.gateway.owner_gate.is_gateway_owner``
         (the single source of truth for owner allowlist / dev BYPASS).

    Tool code MUST call this helper instead of importing
    ``butler.gateway.owner_gate`` directly so that the tools layer does
    not have a hard reverse dependency on the gateway layer.
    """
    orch = get_current_orchestrator()
    is_owner = _orchestrator_explicit_attr(orch, "is_owner") if orch is not None else None
    if callable(is_owner):
        return bool(
            is_owner(
                platform=platform,
                external_id=external_id,
                session_key=session_key,
            )
        )

    gate = get_owner_gate()
    if gate is not None:
        return bool(
            gate.is_gateway_owner(
                platform=platform,
                external_id=external_id,
                session_key=session_key,
            )
        )
    return False


def owner_required_message() -> str:
    """Layering seam (R1-10) — owner-denied message string."""

    gate = get_owner_gate()
    if gate is not None:
        return str(gate.owner_required_message())
    return "此操作需要 Owner 权限。"


def get_current_turn_bridge() -> Any:
    """Layering seam (R1-10) — outbound bridge for the current turn.

    Precedence:

      1. If an orchestrator is bound and has a non-``None``
         ``gateway_bridge`` attribute set on the instance, return it.
      2. Otherwise, use :class:`BridgeAccess` from contracts registry.
      3. Otherwise, fall back to ``get_gateway_bridge_optional()``.

    Tool code MUST call this helper instead of importing
    ``butler.gateway.outbound_bridge`` directly.
    """
    orch = get_current_orchestrator()
    if orch is not None:
        bridge = _orchestrator_explicit_attr(orch, "gateway_bridge")
        if bridge is not None:
            return bridge

    access = get_bridge_access()
    if access is not None:
        return access.get_optional_bridge()
    return None


def try_push_current_turn_workflow_failure(
    workflow_name: str,
    error: "Exception | str",
    *,
    session_key: str = "",
) -> bool:
    """Layering seam (R1-10) — push a workflow-failure completion message."""

    access = get_bridge_access()
    if access is not None:
        return bool(
            access.try_push_workflow_failure(
                workflow_name,
                error,
                session_key=session_key,
            )
        )
    return False
