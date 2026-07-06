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
    return bool(env_truthy("BUTLER_NETWORK_SEARCH_GATE", default=True))


def max_firecrawl_search_per_turn() -> int:
    try:
        return max(0, int(int_env("BUTLER_FIRECRAWL_SEARCH_MAX_PER_TURN", 3, min=0)))
    except ValueError:
        return 3


def max_web_search_empty_per_turn() -> int:
    try:
        return max(0, int(int_env("BUTLER_WEB_SEARCH_EMPTY_MAX_PER_TURN", 2, min=0)))
    except ValueError:
        return 2


def max_firecrawl_agent_per_turn() -> int:
    try:
        return max(0, int(int_env("BUTLER_FIRECRAWL_AGENT_MAX_PER_TURN", 0, min=0)))
    except ValueError:
        return 0


def max_firecrawl_feedback_per_turn() -> int:
    try:
        return max(0, int(int_env("BUTLER_FIRECRAWL_FEEDBACK_MAX_PER_TURN", 0, min=0)))
    except ValueError:
        return 0


def is_firecrawl_agent_tool(tool_name: str) -> bool:
    name = str(tool_name or "").lower()
    return "firecrawl" in name and "agent" in name


def is_firecrawl_feedback_tool(tool_name: str) -> bool:
    name = str(tool_name or "").lower()
    return "firecrawl" in name and "feedback" in name


def is_firecrawl_search_tool(tool_name: str) -> bool:
    name = str(tool_name or "").lower()
    if "feedback" in name or "agent" in name:
        return False
    return "firecrawl" in name and "search" in name


def is_todoist_mcp_intent(query: str) -> bool:
    """Todoist 列项目/任务应走 MCP，不走 web 检索或 API 文档臆造。"""
    text = str(query or "").strip().lower()
    if "todoist" not in text:
        return False
    hints = (
        "项目", "待办", "任务", "inbox", "列出", "哪些", "今天", "明天",
        "project", "task", "list",
    )
    return any(h in text for h in hints)


def is_github_mcp_intent(query: str) -> bool:
    """GitHub 列仓库/issues 应走 MCP，不走 web 检索。"""
    from butler.tools.network_search_policy_ops import is_github_mcp_intent_safe

    return bool(is_github_mcp_intent_safe(query))


def _github_mcp_block(tool_name: str) -> dict[str, Any] | None:
    if not is_github_mcp_intent(_turn_user_query()):
        return None
    name = str(tool_name or "").strip().lower()
    if is_web_search_tool(name) or name == "web_fetch":
        return {
            "ok": False,
            "code": "GITHUB_USE_MCP",
            "error": (
                "GitHub 仓库/issues 须调用 mcp_github_lst_repos_authenticated_usr / "
                "mcp_github_lst_repo_issues 等 MCP 工具，禁止 web_search 或 web_fetch。"
            ),
            "hint": "mcp_github_lst_repos_authenticated_usr · mcp_github_lst_repo_issues",
        }
    return None


def _todoist_mcp_block(tool_name: str) -> dict[str, Any] | None:
    if not is_todoist_mcp_intent(_turn_user_query()):
        return None
    name = str(tool_name or "").strip().lower()
    if is_web_search_tool(name) or name == "web_fetch":
        return {
            "ok": False,
            "code": "TODOIST_USE_MCP",
            "error": (
                "Todoist 查询须调用 mcp_todoist_lst_projects / mcp_todoist_lst_tasks 等 MCP 工具，"
                "禁止 web_search 或 web_fetch 查 API 文档。"
            ),
            "hint": "mcp_todoist_lst_projects · mcp_todoist_lst_tasks",
        }
    return None


def is_web_search_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip().lower() == "web_search"


def is_web_search_intent(query: str) -> bool:
    text = str(query or "").strip()
    if not text:
        return False
    if is_todoist_mcp_intent(text):
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
            "firecrawl_agent_count": 0,
            "firecrawl_feedback_count": 0,
            "web_search_empty_count": 0,
            "inbound_user_text": str(inbound_user_text or "").strip(),
        }
    )
    try:
        yield
    finally:
        _CTX.reset(token)


def _bridge_state() -> Any | None:
    from butler.tools.network_search_policy_ops import get_turn_bridge_safe

    return get_turn_bridge_safe()


def _ctx_state() -> dict[str, Any]:
    bucket = _CTX.get()
    if bucket is None:
        bucket = {
            "web_search_used": False,
            "firecrawl_search_count": 0,
            "firecrawl_agent_count": 0,
            "firecrawl_feedback_count": 0,
            "web_search_empty_count": 0,
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


def _firecrawl_agent_count() -> int:
    bridge = _bridge_state()
    if bridge is not None:
        return int(getattr(bridge, "firecrawl_agent_count", 0) or 0)
    return int(_ctx_state().get("firecrawl_agent_count") or 0)


def _inc_firecrawl_agent_count() -> int:
    bridge = _bridge_state()
    if bridge is not None:
        bridge.firecrawl_agent_count = int(getattr(bridge, "firecrawl_agent_count", 0) or 0) + 1
        return int(bridge.firecrawl_agent_count)
    bucket = _ctx_state()
    bucket["firecrawl_agent_count"] = int(bucket.get("firecrawl_agent_count") or 0) + 1
    return int(bucket["firecrawl_agent_count"])


def _firecrawl_feedback_count() -> int:
    bridge = _bridge_state()
    if bridge is not None:
        return int(getattr(bridge, "firecrawl_feedback_count", 0) or 0)
    return int(_ctx_state().get("firecrawl_feedback_count") or 0)


def _inc_firecrawl_feedback_count() -> int:
    bridge = _bridge_state()
    if bridge is not None:
        bridge.firecrawl_feedback_count = int(getattr(bridge, "firecrawl_feedback_count", 0) or 0) + 1
        return int(bridge.firecrawl_feedback_count)
    bucket = _ctx_state()
    bucket["firecrawl_feedback_count"] = int(bucket.get("firecrawl_feedback_count") or 0) + 1
    return int(bucket["firecrawl_feedback_count"])


def _web_search_empty_count() -> int:
    bridge = _bridge_state()
    if bridge is not None:
        return int(getattr(bridge, "web_search_empty_count", 0) or 0)
    return int(_ctx_state().get("web_search_empty_count") or 0)


def _inc_web_search_empty_count() -> int:
    bridge = _bridge_state()
    if bridge is not None:
        bridge.web_search_empty_count = int(getattr(bridge, "web_search_empty_count", 0) or 0) + 1
        return int(bridge.web_search_empty_count)
    bucket = _ctx_state()
    bucket["web_search_empty_count"] = int(bucket.get("web_search_empty_count") or 0) + 1
    return int(bucket["web_search_empty_count"])


def _turn_user_query() -> str:
    bridge = _bridge_state()
    if bridge is not None:
        text = str(getattr(bridge, "inbound_user_text", "") or "").strip()
        if text:
            return text
    text = str(_ctx_state().get("inbound_user_text") or "").strip()
    if text:
        return text
    from butler.tools.network_search_policy_ops import epoch_user_query_safe

    return str(epoch_user_query_safe())


def _web_search_in_current_toolset() -> bool:
    from butler.tools.web_search import web_search_enabled
    from butler.tools.network_search_policy_ops import web_search_in_current_toolset_safe

    if not web_search_enabled():
        return False
    return bool(web_search_in_current_toolset_safe(fallback=web_search_enabled()))


def _gate_active() -> bool:
    return network_search_gate_enabled() and _web_search_in_current_toolset()


def _firecrawl_aux_block(tool_name: str, *, disabled_code: str, disabled_msg: str, quota_code: str) -> dict[str, Any] | None:
    cap = max_firecrawl_agent_per_turn() if is_firecrawl_agent_tool(tool_name) else max_firecrawl_feedback_per_turn()
    if cap <= 0:
        return {
            "ok": False,
            "code": disabled_code,
            "error": disabled_msg,
            "hint": "勿向用户提及审批流程；用 firecrawl_search 结果的 URL 做 scrape 或直接总结",
        }
    count = _firecrawl_agent_count() if is_firecrawl_agent_tool(tool_name) else _firecrawl_feedback_count()
    if count >= cap:
        return {
            "ok": False,
            "code": quota_code,
            "error": f"本轮该 Firecrawl 工具已达上限（{cap} 次）；请 scrape 已有 URL 或直接总结。",
            "hint": "勿向用户提及审批流程",
        }
    return None


def _firecrawl_gate_block(tool_name: str) -> dict[str, Any] | None:
    """Shared gate for Firecrawl search/agent/feedback on retrieval-intent turns."""
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
    if is_firecrawl_feedback_tool(tool_name):
        return _firecrawl_aux_block(
            tool_name,
            disabled_code="FIRECRAWL_FEEDBACK_DISABLED",
            disabled_msg=(
                "检索任务禁止 mcp_firecrawl_*_feedback；"
                "请根据 firecrawl_search 结果 scrape URL 或直接总结。"
            ),
            quota_code="FIRECRAWL_FEEDBACK_QUOTA",
        )
    if is_firecrawl_agent_tool(tool_name):
        return _firecrawl_aux_block(
            tool_name,
            disabled_code="FIRECRAWL_AGENT_DISABLED",
            disabled_msg=(
                "检索任务禁止 mcp_firecrawl_*_agent（高成本）；"
                "请根据 firecrawl_search 结果 scrape 已有 URL 或直接总结。"
            ),
            quota_code="FIRECRAWL_AGENT_QUOTA",
        )
    cap = max_firecrawl_search_per_turn()
    if cap >= 0 and _firecrawl_search_count() >= cap:
        return {
            "ok": False,
            "code": "FIRECRAWL_SEARCH_QUOTA",
            "error": (
                f"本轮 mcp_firecrawl_*_search 已达上限（{cap} 次）；"
                "请根据已有搜索结果选用 URL 做 scrape，或直接总结。"
            ),
            "hint": "优先 mcp_firecrawl_scrape 已有 URL，勿调 feedback/agent",
        }
    return None


def check_network_search_tool_block(tool_name: str, args: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return error payload if tool call violates network search policy."""
    _ = args
    name = str(tool_name or "").strip()
    github_block = _github_mcp_block(name)
    if github_block is not None:
        return github_block
    todoist_block = _todoist_mcp_block(name)
    if todoist_block is not None:
        return todoist_block
    if not name or not _gate_active():
        return None
    if is_web_search_tool(name):
        if is_web_search_intent(_turn_user_query()):
            cap = max_web_search_empty_per_turn()
            if cap >= 0 and _web_search_empty_count() >= cap:
                return {
                    "ok": False,
                    "code": "WEB_SEARCH_EXHAUSTED",
                    "error": (
                        f"本轮 web_search 已连续空结果 {cap} 次；"
                        "请改用 mcp_firecrawl_firecrawl_search / scrape 或直接总结。"
                    ),
                    "hint": "勿再重复 web_search；Firecrawl 已在 web_search 之后可用",
                }
        return None
    if (
        not is_firecrawl_search_tool(name)
        and not is_firecrawl_agent_tool(name)
        and not is_firecrawl_feedback_tool(name)
    ):
        return None
    return _firecrawl_gate_block(name)


def record_network_search_tool(tool_name: str) -> None:
    """Record web_search / firecrawl search/agent/feedback usage for the current turn."""
    name = str(tool_name or "").strip()
    if is_web_search_tool(name):
        _set_web_search_used()
    elif is_firecrawl_feedback_tool(name):
        _inc_firecrawl_feedback_count()
    elif is_firecrawl_agent_tool(name):
        _inc_firecrawl_agent_count()
    elif is_firecrawl_search_tool(name):
        _inc_firecrawl_search_count()


def note_web_search_outcome(result_text: str) -> None:
    """Track empty web_search results to cap pointless retries."""
    text = str(result_text or "").strip()
    if not text:
        _inc_web_search_empty_count()
        return
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    if payload.get("error"):
        _inc_web_search_empty_count()
        return
    results = payload.get("results")
    if isinstance(results, list) and len(results) == 0:
        _inc_web_search_empty_count()


__all__ = [
    "check_network_search_tool_block",
    "is_firecrawl_agent_tool",
    "is_firecrawl_feedback_tool",
    "is_firecrawl_search_tool",
    "is_github_mcp_intent",
    "is_web_search_intent",
    "is_web_search_tool",
    "max_firecrawl_agent_per_turn",
    "max_firecrawl_feedback_per_turn",
    "max_firecrawl_search_per_turn",
    "max_web_search_empty_per_turn",
    "network_search_gate_enabled",
    "note_web_search_outcome",
    "record_network_search_tool",
    "turn_network_search_scope",
]
