"""Hook MCP tools into butler.tools.registry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

from butler.mcp.bridge import format_call_result, refs_to_openai_definitions
from butler.mcp.config import mcp_enabled, mcp_sdk_available
from butler.mcp.manager import get_manager
from butler.mcp.naming import is_mcp_registered_name
from butler.mcp.registry_hook_ops import (
    extension_verify_status_lines_safe,
    is_plan_mode_active,
    maybe_deferred_mcp_definitions,
    mcp_config_count_safe,
    mcp_warmup_safe,
    resolve_session_key_for_connect,
    resolve_workspace_safe,
    run_mcp_with_gates_or_direct,
    session_key_fallback,
)
from butler.mcp.turn_scrape_dedup import is_firecrawl_scrape_tool
from butler.mcp.classify import is_mutating_classification

logger = logging.getLogger(__name__)


def is_mcp_tool(name: str) -> bool:
    return bool(is_mcp_registered_name(name))


def _resolve_workspace() -> Path | None:
    return cast(Path | None, resolve_workspace_safe())


def ensure_mcp_for_session(session_key: str = "") -> list[dict[str, Any]]:
    if not mcp_enabled():
        return []
    sk = resolve_session_key_for_connect(session_key)
    refs = get_manager().ensure_connected(sk, workspace=_resolve_workspace())
    return cast(list[dict[str, Any]], refs_to_openai_definitions(refs))


def get_mcp_tool_definitions(session_key: str = "") -> list[dict[str, Any]]:
    deferred = maybe_deferred_mcp_definitions(session_key)
    if deferred is not None:
        return cast(list[dict[str, Any]], deferred)
    return ensure_mcp_for_session(session_key)


def disconnect_mcp_session(session_key: str) -> None:
    if not mcp_sdk_available():
        return
    get_manager().disconnect_session(session_key)


def check_plan_mode_mcp_block(tool_name: str, *, session_key: str = "") -> str | None:
    if not is_mcp_tool(tool_name):
        return None
    if is_plan_mode_active(session_key) is not True:
        return None
    ref = get_manager().get_tool_ref(
        session_key or session_key_fallback(),
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
    return cast(str, session_key_fallback())


def dispatch_mcp_tool(name: str, args: dict[str, Any]) -> str | None:
    """Return result string if this is an MCP tool; None to fall through."""
    resolved_name = name
    normalized_args = args
    if str(name or "").startswith("mcp_github_"):
        from butler.mcp.github_tool_aliases import (
            normalize_github_mcp_args,
            resolve_github_mcp_tool_name,
        )

        resolved_name = resolve_github_mcp_tool_name(name)
        normalized_args = normalize_github_mcp_args(
            resolved_name,
            args if isinstance(args, dict) else {},
            user_text="",
        )
    elif str(name or "").startswith("mcp_todoist_"):
        from butler.mcp.todoist_tool_aliases import (
            normalize_todoist_mcp_args,
            resolve_todoist_mcp_tool_name,
        )

        resolved_name = resolve_todoist_mcp_tool_name(name)
        normalized_args = normalize_todoist_mcp_args(
            resolved_name,
            args if isinstance(args, dict) else {},
        )
    if not mcp_enabled() or not is_mcp_tool(resolved_name):
        return None
    if not mcp_sdk_available():
        return json.dumps({
            "ok": False,
            "error": "MCP SDK not installed. pip install butler-system[mcp]",
            "code": "MCP_SDK_MISSING",
        }, ensure_ascii=False)

    plan_block = check_plan_mode_mcp_block(resolved_name)
    if plan_block:
        return json.dumps({
            "ok": False,
            "error": plan_block,
            "code": "PLAN_MODE_BLOCKED",
        }, ensure_ascii=False)

    if not isinstance(normalized_args, dict):
        normalized_args = {}

    if is_firecrawl_scrape_tool(resolved_name):
        from butler.mcp.turn_scrape_dedup import (
            check_and_record_scrape,
            scrape_url_from_args,
        )

        dup = check_and_record_scrape(scrape_url_from_args(normalized_args))
        if dup:
            return json.dumps({
                "ok": False,
                "error": dup,
                "code": "MCP_SCRAPE_DUPLICATE",
            }, ensure_ascii=False)

    sk = _session_key_fallback()
    ref = get_manager().get_tool_ref(sk, resolved_name)
    if ref is None:
        ensure_mcp_for_session(sk)
        ref = get_manager().get_tool_ref(sk, resolved_name)
    if ref is None:
        return json.dumps({
            "ok": False,
            "error": f"Unknown MCP tool: {name}",
            "code": "MCP_TOOL_UNKNOWN",
        }, ensure_ascii=False)

    def _call() -> str:
        return cast(
            str,
            get_manager().call_tool(sk, ref, normalized_args, workspace=_resolve_workspace()),
        )

    text = run_mcp_with_gates_or_direct(
        server_id=ref.server_id,
        tool_name=resolved_name,
        args=normalized_args,
        session_key=sk,
        classification=str(ref.classification or ""),
        run_fn=_call,
    )
    if text.strip().startswith("{") and '"ok": false' in text.replace(" ", "").lower():
        return cast(str | None, text)
    return cast(str | None, format_call_result(text, tool_name=resolved_name, server_id=ref.server_id))


def mcp_status_lines(session_key: str = "") -> list[str]:
    from butler.mcp.config import mcp_enabled as enabled_fn

    if not enabled_fn():
        return ["MCP: 已关闭 (BUTLER_MCP_ENABLED=0 或未安装 butler-system[mcp])"]
    if not mcp_sdk_available():
        return ["MCP: 已开启但缺少 SDK (pip install butler-system[mcp])"]
    sk = str(session_key or _session_key_fallback()).strip() or "default"
    mgr = get_manager()
    workspace = _resolve_workspace()
    # /诊断 须在首条 agent 消息前也能看到 MCP 状态；ensure_connected 与工具派发同源。
    mcp_warmup_safe(mgr, sk, workspace)
    statuses = mgr.status_snapshot(sk)
    if not statuses:
        cfg_count = mcp_config_count_safe(workspace) or 0
        if cfg_count == 0:
            return ["MCP: 已开启，mcp.yaml 无 server 配置（检查 ~/.butler/mcp.yaml）"]
        return ["MCP: 已开启，server 均未连接（见上方日志或重试 /诊断）"]
    lines = ["MCP: 已开启"]
    for st in statuses:
        mark = "ok" if st.connected else "down"
        err = f" · {st.last_error[:80]}" if st.last_error else ""
        lines.append(
            f"  - {st.server_id} ({st.transport}) [{mark}] tools={st.tool_count}{err}"
        )
    lines.extend(extension_verify_status_lines_safe())
    return lines
