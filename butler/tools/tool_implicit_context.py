"""Inject implicit Butler context into tool dispatch args (support line E)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy


def implicit_context_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_IMPLICIT_CONTEXT", default=True)


def resolve_project_workspace() -> Path | None:
    from butler.tools.tool_implicit_context_ops import resolve_project_workspace_safe

    return resolve_project_workspace_safe()


def build_implicit_tool_args() -> dict[str, Any]:
    """Keys prefixed with ``_butler_`` — stripped from LLM schemas, passed to handlers via ``**_``."""
    from butler.tools.tool_implicit_context_ops import (
        current_session_key_safe,
        current_workflow_step_safe,
    )

    if not implicit_context_enabled():
        return {}
    out: dict[str, Any] = {}
    sk = current_session_key_safe()
    if sk:
        out["_butler_session_key"] = sk
    ws = resolve_project_workspace()
    if ws is not None:
        out["_butler_project_root"] = str(ws)
        out["_butler_workspace"] = str(ws)
    step = current_workflow_step_safe()
    if step:
        out["_butler_workflow_step"] = step
    return out


def merge_implicit_tool_args(args: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(args or {})
    for key, val in build_implicit_tool_args().items():
        merged.setdefault(key, val)
    return merged


__all__ = [
    "build_implicit_tool_args",
    "implicit_context_enabled",
    "merge_implicit_tool_args",
    "resolve_project_workspace",
]
