"""Hook MCP tools into butler.tools.registry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.mcp.bridge import format_call_result, refs_to_openai_definitions
from butler.mcp.config import mcp_enabled, mcp_sdk_available
from butler.mcp.manager import get_manager
from butler.mcp.naming import is_mcp_registered_name
from butler.mcp.classify import is_mutating_classification

logger = logging.getLogger(__name__)


def is_mcp_tool(name: str) -> bool:
    return is_mcp_registered_name(name)


def _resolve_workspace() -> Path | None:
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
        return Path(proj.workspace)
    except Exception:
        return None


def ensure_mcp_for_session(session_key: str = "") -> list[dict[str, Any]]:
    if not mcp_enabled():
        return []
    try:
        from butler.execution_context import get_current_session_key

        sk = str(session_key or get_current_session_key() or "").strip() or "default"
    except Exception:
        sk = str(session_key or "default").strip() or "default"
    refs = get_manager().ensure_connected(sk, workspace=_resolve_workspace())
    return refs_to_openai_definitions(refs)


def get_mcp_tool_definitions(session_key: str = "") -> list[dict[str, Any]]:
    try:
        from butler.core.harness_flags import mcp_deferred_tools_enabled
        from butler.mcp.deferred import get_deferred_mcp_definitions

        if mcp_deferred_tools_enabled():
            return get_deferred_mcp_definitions(session_key)
    except Exception as exc:
        logger.debug("MCP deferred definitions skipped: %s", exc)
    return ensure_mcp_for_session(session_key)


def disconnect_mcp_session(session_key: str) -> None:
    if not mcp_sdk_available():
        return
    get_manager().disconnect_session(session_key)


def check_plan_mode_mcp_block(tool_name: str, *, session_key: str = "") -> str | None:
    if not is_mcp_tool(tool_name):
        return None
    try:
        from butler.plan.mode import is_plan_mode

        if not is_plan_mode(session_key):
            return None
    except Exception:
        return None
    ref = get_manager().get_tool_ref(
        session_key or _session_key_fallback(),
        tool_name,
    )
    if ref is None:
        return None
    if is_mutating_classification(ref.classification):
        return (
            f"规划模式下 MCP 工具「{tool_name}」已禁用（{ref.classification}）。"
            "只读 MCP 工具仍可用。"
        )
    return None


def _session_key_fallback() -> str:
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"
    except Exception:
        return "default"


def dispatch_mcp_tool(name: str, args: dict[str, Any]) -> str | None:
    """Return result string if this is an MCP tool; None to fall through."""
    if not mcp_enabled() or not is_mcp_tool(name):
        return None
    if not mcp_sdk_available():
        return json.dumps({
            "ok": False,
            "error": "MCP SDK not installed. pip install butler-system[mcp]",
            "code": "MCP_SDK_MISSING",
        }, ensure_ascii=False)

    plan_block = check_plan_mode_mcp_block(name)
    if plan_block:
        return json.dumps({
            "ok": False,
            "error": plan_block,
            "code": "PLAN_MODE_BLOCKED",
        }, ensure_ascii=False)

    sk = _session_key_fallback()
    ref = get_manager().get_tool_ref(sk, name)
    if ref is None:
        ensure_mcp_for_session(sk)
        ref = get_manager().get_tool_ref(sk, name)
    if ref is None:
        return json.dumps({
            "ok": False,
            "error": f"Unknown MCP tool: {name}",
            "code": "MCP_TOOL_UNKNOWN",
        }, ensure_ascii=False)

    if not isinstance(args, dict):
        args = {}

    def _call() -> str:
        return get_manager().call_tool(sk, ref, args, workspace=_resolve_workspace())

    try:
        from butler.core.tool_orchestrator import run_mcp_with_gates

        text = run_mcp_with_gates(
            server_id=ref.server_id,
            tool_name=name,
            args=args,
            session_key=sk,
            classification=str(ref.classification or ""),
            run_fn=_call,
        )
    except Exception:
        text = _call()
    if text.strip().startswith("{") and '"ok": false' in text.replace(" ", "").lower():
        return text
    return format_call_result(text, tool_name=name, server_id=ref.server_id)


def mcp_status_lines(session_key: str = "") -> list[str]:
    from butler.mcp.config import mcp_enabled as enabled_fn

    if not enabled_fn():
        return ["MCP: 已关闭 (BUTLER_MCP_ENABLED=0 或未安装 butler-system[mcp])"]
    if not mcp_sdk_available():
        return ["MCP: 已开启但缺少 SDK (pip install butler-system[mcp])"]
    sk = str(session_key or _session_key_fallback()).strip() or "default"
    statuses = get_manager().status_snapshot(sk)
    if not statuses:
        return ["MCP: 已开启，无已连接 server（检查 ~/.butler/mcp.yaml）"]
    lines = ["MCP: 已开启"]
    for st in statuses:
        mark = "ok" if st.connected else "down"
        err = f" · {st.last_error[:80]}" if st.last_error else ""
        lines.append(
            f"  - {st.server_id} ({st.transport}) [{mark}] tools={st.tool_count}{err}"
        )
    return lines
