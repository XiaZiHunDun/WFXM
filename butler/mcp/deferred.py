"""MCP deferred tool discovery — compact catalog + on-demand schema load (PR-X4)."""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from butler.core.harness_flags import mcp_deferred_tools_enabled
from butler.mcp.bridge import refs_to_openai_definitions
from butler.mcp.config import mcp_enabled
from butler.mcp.naming import is_mcp_registered_name

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_promoted: dict[str, set[str]] = {}


def _session_key(session_key: str = "") -> str:
    key = str(session_key or "").strip()
    if key:
        return key
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"
    except Exception:
        return "default"


def get_promoted_tools(session_key: str = "") -> set[str]:
    sk = _session_key(session_key)
    with _lock:
        return set(_promoted.get(sk) or ())


def promote_tools(names: list[str], *, session_key: str = "") -> list[str]:
    sk = _session_key(session_key)
    added: list[str] = []
    with _lock:
        bucket = _promoted.setdefault(sk, set())
        for raw in names:
            name = str(raw or "").strip()
            if not name or not is_mcp_registered_name(name):
                continue
            if name not in bucket:
                bucket.add(name)
                added.append(name)
    return added


def _tool_def_name(defn: dict[str, Any]) -> str:
    fn = defn.get("function") if isinstance(defn.get("function"), dict) else {}
    return str(fn.get("name") or defn.get("name") or "").strip()


def promote_experience_mcp_tools(
    names: list[str],
    *,
    session_key: str = "",
) -> tuple[list[str], list[dict[str, str]]]:
    """Validate MCP refs exist, then promote. Returns ``(added, rejected)``."""
    sk = _session_key(session_key)
    cleaned = [str(n or "").strip() for n in (names or []) if str(n or "").strip()]
    if not cleaned:
        return [], []

    if not mcp_enabled():
        return [], [{"name": n, "reason": "mcp_disabled"} for n in cleaned]

    rejected: list[dict[str, str]] = []
    to_promote: list[str] = []
    try:
        _all_mcp_refs(sk)
    except Exception as exc:  # noqa: BLE001 — surface connect failure
        logger.debug("MCP connect for experience promote failed: %s", exc)
        return [], [{"name": n, "reason": "connect_failed"} for n in cleaned]

    from butler.mcp.manager import get_manager

    mgr = get_manager()
    for name in cleaned:
        if not is_mcp_registered_name(name):
            rejected.append({"name": name, "reason": "invalid_registered_name"})
            continue
        if mgr.get_tool_ref(sk, name) is None:
            rejected.append({"name": name, "reason": "tool_not_found"})
            continue
        to_promote.append(name)

    added = promote_tools(to_promote, session_key=sk)
    return added, rejected


def merge_deferred_mcp_into_turn_tools(
    tools: list[dict[str, Any]],
    *,
    session_key: str = "",
) -> list[dict[str, Any]]:
    """Append promoted MCP OpenAI schemas to the per-turn tool list."""
    mcp_defs = get_deferred_mcp_definitions(session_key)
    if not mcp_defs:
        return tools
    seen = {_tool_def_name(t) for t in tools if _tool_def_name(t)}
    out = list(tools)
    for defn in mcp_defs:
        name = _tool_def_name(defn)
        if name and name not in seen:
            out.append(defn)
            seen.add(name)
    return out


def clear_promoted(session_key: str = "") -> None:
    sk = _session_key(session_key)
    with _lock:
        _promoted.pop(sk, None)


def _resolve_workspace() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch else None
        if pm is None:
            return None
        from butler.execution_context import get_current_session_key

        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        return Path(proj.workspace)
    except Exception:
        return None


def _all_mcp_refs(session_key: str = ""):
    from butler.mcp.manager import get_manager

    sk = _session_key(session_key)
    return get_manager().ensure_connected(sk, workspace=_resolve_workspace())


def search_mcp_tools(
    query: str,
    *,
    limit: int = 12,
    session_key: str = "",
) -> list[dict[str, Any]]:
    if not mcp_enabled():
        return []
    q = str(query or "").strip().lower()
    refs = _all_mcp_refs(session_key)
    scored: list[tuple[int, Any]] = []
    for ref in refs:
        hay = f"{ref.registered_name} {ref.original_name} {ref.description}".lower()
        if not q:
            score = 0
        elif q in hay:
            score = 2 if q in ref.registered_name.lower() else 1
        else:
            tokens = [t for t in re.split(r"\W+", q) if len(t) >= 2]
            score = sum(1 for t in tokens if t in hay)
        if q and score <= 0:
            continue
        scored.append((score, ref))
    scored.sort(key=lambda x: (-x[0], x[1].registered_name))
    out: list[dict[str, Any]] = []
    for _, ref in scored[: max(1, min(50, int(limit)))]:
        out.append({
            "registered_name": ref.registered_name,
            "server_id": ref.server_id,
            "original_name": ref.original_name,
            "classification": ref.classification,
            "description": (ref.description or "")[:240],
        })
    return out


def get_deferred_mcp_definitions(session_key: str = "") -> list[dict[str, Any]]:
    """Full OpenAI schemas only for session-promoted MCP tools."""
    if not mcp_enabled() or not mcp_deferred_tools_enabled():
        return []
    sk = _session_key(session_key)
    promoted = get_promoted_tools(sk)
    if not promoted:
        return []
    refs = [r for r in _all_mcp_refs(sk) if r.registered_name in promoted]
    return refs_to_openai_definitions(refs)


def tool_search_handler(query: str, limit: int = 12, promote: bool = False) -> str:
    matches = search_mcp_tools(query, limit=limit)
    promoted: list[str] = []
    if promote and matches:
        promoted = promote_tools(
            [str(m.get("registered_name") or "") for m in matches],
            session_key=_session_key(),
        )
    return json.dumps(
        {
            "ok": True,
            "code": "MCP_TOOL_SEARCH",
            "query": query,
            "count": len(matches),
            "tools": matches,
            "promoted": promoted,
        },
        ensure_ascii=False,
    )


def load_mcp_tools_handler(tool_names: list[str]) -> str:
    names = [str(n or "").strip() for n in (tool_names or []) if str(n or "").strip()]
    added = promote_tools(names, session_key=_session_key())
    return json.dumps(
        {
            "ok": True,
            "code": "MCP_LOAD_TOOLS",
            "promoted": added,
            "session_promoted": sorted(get_promoted_tools(_session_key())),
        },
        ensure_ascii=False,
    )


__all__ = [
    "clear_promoted",
    "get_deferred_mcp_definitions",
    "get_promoted_tools",
    "load_mcp_tools_handler",
    "merge_deferred_mcp_into_turn_tools",
    "promote_experience_mcp_tools",
    "promote_tools",
    "search_mcp_tools",
    "tool_search_handler",
]
