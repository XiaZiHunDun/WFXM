"""Provider-specific tool call wire helpers (PR-X3 / 主线 K)."""

from __future__ import annotations

import json
import logging
from typing import Any

from butler.env_parse import env_truthy
from butler.transport.model_capabilities import get_provider_capabilities
from butler.transport.types import ToolCall

logger = logging.getLogger(__name__)


def tool_wire_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_WIRE", default=True)


def _provider_key(provider: str) -> str:
    return str(provider or "").strip().lower()


def wire_tools_for_provider(
    provider: str,
    tools: list[dict[str, Any]] | None,
    *,
    api_mode: str = "",
) -> list[dict[str, Any]] | None:
    """Convert OpenAI-style tool defs for the active provider transport."""
    if not tools:
        return None
    if not tool_wire_enabled():
        return tools
    from butler.transport import get_transport

    mode = api_mode
    if not mode:
        cap = get_provider_capabilities(provider)
        style = str(cap.get("tool_choice_style") or "openai")
        mode = "anthropic_messages" if style == "anthropic" else "openai"
    transport = get_transport(mode)
    if transport is None:
        return tools
    from butler.transport.tool_wire_ops import convert_provider_tools_safe

    return convert_provider_tools_safe(transport, tools)


def normalize_tool_calls_for_provider(
    provider: str,
    tool_calls: list[ToolCall] | None,
) -> list[ToolCall]:
    """Normalize IDs and argument JSON strings per provider quirks."""
    if not tool_calls:
        return []
    if not tool_wire_enabled():
        return list(tool_calls)
    key = _provider_key(provider)
    out: list[ToolCall] = []
    for tc in tool_calls:
        args = tc.arguments
        if isinstance(args, dict):
            args = json.dumps(args, ensure_ascii=False)
        elif args is None:
            args = "{}"
        else:
            args = str(args)
        if key == "anthropic" and not str(args).strip():
            args = "{}"
        tid = tc.id
        if key == "anthropic" and not tid:
            import uuid

            tid = f"toolu_{uuid.uuid4().hex[:12]}"
        out.append(
            ToolCall(
                id=tid,
                name=str(tc.name or ""),
                arguments=args,
                provider_data=tc.provider_data,
            )
        )
    return out


def format_tool_result_message(
    provider: str,
    *,
    tool_call_id: str,
    name: str,
    content: str,
) -> dict[str, Any]:
    """Build an OpenAI-style tool message (transport may reshape on send)."""
    _ = name
    msg: dict[str, Any] = {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }
    if tool_wire_enabled() and _provider_key(provider) == "anthropic":
        msg["_wire_provider"] = "anthropic"
    return msg


def parse_tool_calls_from_raw(
    provider: str,
    raw_tool_calls: list[Any],
) -> list[ToolCall]:
    """Best-effort parse of provider-native tool call objects into ToolCall."""
    out: list[ToolCall] = []
    for item in raw_tool_calls or []:
        if isinstance(item, ToolCall):
            out.append(item)
            continue
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if isinstance(item.get("function"), dict) else item
        name = ""
        arguments = "{}"
        if isinstance(fn, dict):
            name = str(fn.get("name") or item.get("name") or "")
            arguments = fn.get("arguments", item.get("arguments", "{}"))
        else:
            name = str(item.get("name") or "")
            arguments = item.get("arguments", item.get("input", "{}"))
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments, ensure_ascii=False)
        out.append(
            ToolCall(
                id=str(item.get("id") or ""),
                name=name,
                arguments=str(arguments or "{}"),
                provider_data={"raw": item},
            )
        )
    return normalize_tool_calls_for_provider(provider, out)


__all__ = [
    "format_tool_result_message",
    "normalize_tool_calls_for_provider",
    "parse_tool_calls_from_raw",
    "tool_wire_enabled",
    "wire_tools_for_provider",
]
