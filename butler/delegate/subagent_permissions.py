"""Subagent tool filtering (OpenCode deriveSubagentSessionPermission subset)."""

from __future__ import annotations

from pathlib import Path

from typing import Any

from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
from butler.permissions.rules import _load_permissions_yaml
from butler.tools.pim_schema import ALL_PIM_TOOLS

_DEFAULT_SUBAGENT_DENY = frozenset({
    "delegate_task",
    "run_workflow",
    "run_runtime_job",
    "session_todos_list",
    "session_todos_write",
})


def filter_tools_for_subagent(
    tools: list[dict[str, Any]],
    *,
    workspace: Path | None = None,
    role: str = "",
) -> list[dict[str, Any]]:
    """Narrow tool list for delegate_task child loops."""
    cfg = _load_permissions_yaml(workspace)
    sub_cfg = cfg.get("delegate_subagent")
    if not isinstance(sub_cfg, dict):
        sub_cfg = {}

    allow_only = sub_cfg.get("allow_tools")
    if isinstance(allow_only, list) and allow_only:
        allow_set = {str(t).strip() for t in allow_only if str(t).strip()}
        return [
            t
            for t in tools
            if str((t.get("function") or {}).get("name") or "") in allow_set
        ]

    denied = set(_DEFAULT_SUBAGENT_DENY) | set(DELEGATE_BLOCKED_TOOLS)
    extra = sub_cfg.get("deny_tools")
    if isinstance(extra, list):
        denied.update(str(t).strip() for t in extra if str(t).strip())

    role_key = str(role or "").strip().lower()
    # T3 enforcement: non-butler roles must never receive PIM tools.
    if role_key not in ("butler", "default", ""):
        denied |= ALL_PIM_TOOLS
    by_role = sub_cfg.get("roles")
    if isinstance(by_role, dict) and role_key:
        role_cfg = by_role.get(role_key)
        if isinstance(role_cfg, dict):
            role_allow = role_cfg.get("allow_tools")
            if isinstance(role_allow, list) and role_allow:
                allow_set = {str(t).strip() for t in role_allow if str(t).strip()}
                return [
                    t
                    for t in tools
                    if str((t.get("function") or {}).get("name") or "") in allow_set
                ]
            role_deny = role_cfg.get("deny_tools")
            if isinstance(role_deny, list):
                denied.update(str(t).strip() for t in role_deny if str(t).strip())

    filtered: list[dict[str, Any]] = []
    for t in tools:
        name = str((t.get("function") or {}).get("name") or "")
        if name in denied:
            continue
        from butler.delegate.subagent_permissions_ops import is_mcp_registered_name_safe

        mcp_registered = is_mcp_registered_name_safe(name)
        if mcp_registered is True:
            continue
        filtered.append(t)
    return filtered


def make_child_session_key(parent_session_key: str, task_id: str) -> str:
    parent = str(parent_session_key or "").strip() or "default"
    tid = str(task_id or "").strip()
    if not tid:
        return parent
    return f"{parent}::delegate::{tid}"
