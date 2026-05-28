"""Inject implicit Butler context into tool dispatch args (support line E)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy
import logging


logger = logging.getLogger(__name__)

def implicit_context_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_IMPLICIT_CONTEXT", default=True)


def resolve_project_workspace() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        return Path(proj.workspace).expanduser().resolve()
    except Exception:
        return None


def build_implicit_tool_args() -> dict[str, Any]:
    """Keys prefixed with ``_butler_`` — stripped from LLM schemas, passed to handlers via ``**_``."""
    if not implicit_context_enabled():
        return {}
    out: dict[str, Any] = {}
    try:
        from butler.execution_context import get_current_session_key

        sk = str(get_current_session_key() or "").strip()
        if sk:
            out["_butler_session_key"] = sk
    except Exception as exc:
        logger.debug("build implicit tool args skipped: %s", exc)
    ws = resolve_project_workspace()
    if ws is not None:
        out["_butler_project_root"] = str(ws)
        out["_butler_workspace"] = str(ws)
    try:
        from butler.execution_context import get_current_workflow_step

        step = str(get_current_workflow_step() or "").strip()
        if step:
            out["_butler_workflow_step"] = step
    except Exception as exc:
        logger.debug("build implicit tool args skipped: %s", exc)
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
