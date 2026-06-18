"""Per-turn network search policy: web_search-first gate + Firecrawl search quota."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from butler.env_parse import env_truthy, int_env

_CTX: ContextVar[dict[str, Any] | None] = ContextVar("network_search_turn", default=None)

_SEARCH_INTENT_RE = re.compile(
    r"(搜(索|一下)?|查(一下|询)?|竞品|竟品|调研|检索|对比|排行|"
    r"competitor|research|lookup|\bsearch\b)",
    re.IGNORECASE,
)


def network_search_gate_enabled() -> bool:
    return env_truthy("BUTLER_NETWORK_SEARCH_GATE", default=True)


def max_firecrawl_search_per_turn() -> int:
    try:
        return max(0, int_env("BUTLER_FIRECRAWL_SEARCH_MAX_PER_TURN", 3, min=0))
    except ValueError:
        return 3


def is_firecrawl_search_tool(tool_name: str) -> bool:
    name = str(tool_name or "").lower()
    return "firecrawl" in name and "search" in name


def is_web_search_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip().lower() == "web_search"


def is_web_search_intent(query: str) -> bool:
    text = str(query or "").strip()
    if not text:
        return False
    if _SEARCH_INTENT_RE.search(text):
        return True
    if "## 相关知识" in text:
        tail = text.split("## 相关知识", 1)[0].strip()
        if tail and _SEARCH_INTENT_RE.search(tail):
            return True
    return False


@contextmanager
def turn_network_search_scope(inbound_user_text: str = "") -> Iterator[None]:
    """Reset per-turn counters (agent loop); gateway also resets bridge fields."""
    token = _CTX.set(
        {
            "web_search_used": False,
            "firecrawl_search_count": 0,
            "inbound_user_text": str(inbound_user_text or "").strip(),
        }
    )
    try:
        yield
    finally:
        _CTX.reset(token)


def _bridge_state() -> Any | None:
    try:
        from butler.execution_context import get_current_turn_bridge

        return get_current_turn_bridge()
    except Exception:
        return None


def _ctx_state() -> dict[str, Any]:
    bucket = _CTX.get()
    if bucket is None:
        bucket = {
            "web_search_used": False,
            "firecrawl_search_count": 0,
            "inbound_user_text": "",
        }
        _CTX.set(bucket)
    return bucket


def _web_search_used() -> bool:
    bridge = _bridge_state()
    if bridge is not None:
        return bool(getattr(bridge, "network_search_web_used", False))
    return bool(_ctx_state().get("web_search_used"))


def _set_web_search_used() -> None:
    bridge = _bridge_state()
    if bridge is not None:
        bridge.network_search_web_used = True
    _ctx_state()["web_search_used"] = True


def _firecrawl_search_count() -> int:
    bridge = _bridge_state()
    if bridge is not None:
        return int(getattr(bridge, "firecrawl_search_count", 0) or 0)
    return int(_ctx_state().get("firecrawl_search_count") or 0)


def _inc_firecrawl_search_count() -> int:
    bridge = _bridge_state()
    if bridge is not None:
        bridge.firecrawl_search_count = int(getattr(bridge, "firecrawl_search_count", 0) or 0) + 1
        return int(bridge.firecrawl_search_count)
    bucket = _ctx_state()
    bucket["firecrawl_search_count"] = int(bucket.get("firecrawl_search_count") or 0) + 1
    return int(bucket["firecrawl_search_count"])


def _turn_user_query() -> str:
    bridge = _bridge_state()
    if bridge is not None:
        text = str(getattr(bridge, "inbound_user_text", "") or "").strip()
        if text:
            return text
    text = str(_ctx_state().get("inbound_user_text") or "").strip()
    if text:
        return text
    try:
        from butler.core.session_epoch import last_user_query_in_epoch
        from butler.execution_context import get_current_session_key

        sk = str(get_current_session_key() or "").strip()
        if sk:
            return last_user_query_in_epoch(sk)
    except Exception:
        pass
    return ""


def _web_search_in_current_toolset() -> bool:
    from butler.tools.web_search import web_search_enabled

    if not web_search_enabled():
        return False
    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key
        from butler.tools.project_tools import get_tool_definitions_for_project

        orch = get_current_orchestrator()
        if orch is None:
            return True
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return True
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        for role in ("lead", "butler", "content", "dev", "review"):
            tools = get_tool_definitions_for_project(proj, role=role)
            names = {
                str((t.get("function") or {}).get("name") or "")
                for t in tools
                if isinstance(t, dict)
            }
            if "web_search" in names:
                return True
        return False
    except Exception:
        return web_search_enabled()


def _gate_active() -> bool:
    return network_search_gate_enabled() and _web_search_in_current_toolset()


def check_network_search_tool_block(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return error payload if tool call violates network search policy."""
    _ = args
    name = str(tool_name or "").strip()
    if not name or not _gate_active():
        return None
    if is_web_search_tool(name):
        return None
    if not is_firecrawl_search_tool(name):
        return None
    if not is_web_search_intent(_turn_user_query()):
        return None

    if not _web_search_used():
        return {
            "ok": False,
            "code": "WEB_SEARCH_REQUIRED",
            "error": (
                "本轮须先用 web_search 检索链接，再调用 Firecrawl search/scrape；"
                "请改用 web_search(query=...) 获取 URL 列表。"
            ),
            "hint": "deep-research：web_search → web_fetch / mcp_firecrawl_scrape",
        }

    cap = max_firecrawl_search_per_turn()
    if cap >= 0 and _firecrawl_search_count() >= cap:
        return {
            "ok": False,
            "code": "FIRECRAWL_SEARCH_QUOTA",
            "error": (
                f"本轮 mcp_firecrawl_*_search 已达上限（{cap} 次）；"
                "请根据已有搜索结果选用 URL 做 scrape，或直接总结。"
            ),
        }
    return None


def record_network_search_tool(tool_name: str) -> None:
    """Record web_search / firecrawl_search usage for the current turn."""
    name = str(tool_name or "").strip()
    if is_web_search_tool(name):
        _set_web_search_used()
    elif is_firecrawl_search_tool(name):
        _inc_firecrawl_search_count()


__all__ = [
    "check_network_search_tool_block",
    "is_firecrawl_search_tool",
    "is_web_search_intent",
    "is_web_search_tool",
    "max_firecrawl_search_per_turn",
    "network_search_gate_enabled",
    "record_network_search_tool",
    "turn_network_search_scope",
]
