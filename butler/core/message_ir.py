"""Canonical message IR for multi-channel inbound (PR-X3 / 主线 K)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from butler.env_parse import env_truthy


class BlockKind(str, Enum):
    TEXT = "text"
    TOOL_RESULT = "tool_result"
    METADATA = "metadata"


@dataclass
class ContentBlock:
    kind: BlockKind
    text: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalMessage:
    """Provider-neutral inbound message."""

    role: str
    blocks: list[ContentBlock] = field(default_factory=list)
    channel: str = ""
    external_id: str = ""
    session_key: str = ""

    def primary_text(self) -> str:
        parts = [b.text for b in self.blocks if b.kind == BlockKind.TEXT and b.text.strip()]
        return "\n".join(parts).strip()


def message_ir_enabled() -> bool:
    return bool(env_truthy("BUTLER_MESSAGE_IR", default=True))
ConverterFn = Callable[[Any], CanonicalMessage]

_CONVERTERS: dict[str, ConverterFn] = {}
_CONVERTER_LOCK = threading.RLock()


def register_converter(channel: str, fn: ConverterFn) -> None:
    key = str(channel or "").strip().lower()
    if key:
        with _CONVERTER_LOCK:
            _CONVERTERS[key] = fn


def convert_inbound(channel: str, payload: Any) -> CanonicalMessage:
    key = str(channel or "").strip().lower() or "text"
    with _CONVERTER_LOCK:
        fn = _CONVERTERS.get(key)
    if fn is not None:
        return fn(payload)
    if isinstance(payload, CanonicalMessage):
        return payload
    if isinstance(payload, str):
        return CanonicalMessage(role="user", blocks=[ContentBlock(BlockKind.TEXT, text=payload)])
    if isinstance(payload, dict) and "blocks" in payload:
        blocks = []
        for raw in payload.get("blocks") or []:
            if not isinstance(raw, dict):
                continue
            kind = BlockKind(str(raw.get("kind") or BlockKind.TEXT.value))
            blocks.append(
                ContentBlock(
                    kind=kind,
                    text=str(raw.get("text") or ""),
                    tool_call_id=str(raw.get("tool_call_id") or ""),
                    tool_name=str(raw.get("tool_name") or ""),
                    meta=dict(raw.get("meta") or {}),
                )
            )
        return CanonicalMessage(
            role=str(payload.get("role") or "user"),
            blocks=blocks,
            channel=str(payload.get("channel") or ""),
            external_id=str(payload.get("external_id") or ""),
            session_key=str(payload.get("session_key") or ""),
        )
    text = str(payload or "")
    return CanonicalMessage(role="user", blocks=[ContentBlock(BlockKind.TEXT, text=text)])


def wechat_inbound(
    text: str,
    *,
    platform: str = "wechat",
    external_id: str = "",
    session_key: str = "",
) -> CanonicalMessage:
    return CanonicalMessage(
        role="user",
        blocks=[ContentBlock(BlockKind.TEXT, text=str(text or ""))],
        channel=platform,
        external_id=str(external_id or ""),
        session_key=str(session_key or ""),
    )


def openai_message_to_ir(msg: dict[str, Any]) -> CanonicalMessage:
    role = str(msg.get("role") or "user")
    blocks: list[ContentBlock] = []
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        blocks.append(ContentBlock(BlockKind.TEXT, text=content))
    elif isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = str(part.get("type") or "")
            if ptype in ("text", "input_text"):
                blocks.append(ContentBlock(BlockKind.TEXT, text=str(part.get("text") or "")))
    if role == "tool":
        blocks.append(
            ContentBlock(
                BlockKind.TOOL_RESULT,
                text=str(content or ""),
                tool_call_id=str(msg.get("tool_call_id") or ""),
                tool_name=str(msg.get("name") or ""),
            )
        )
    if not blocks:
        blocks.append(ContentBlock(BlockKind.TEXT, text=str(content or "")))
    return CanonicalMessage(role=role, blocks=blocks)


def ir_to_openai_user(msg: CanonicalMessage) -> dict[str, Any]:
    text = msg.primary_text()
    out: dict[str, Any] = {"role": "user", "content": text}
    meta_bits = {k: v for k, v in {
        "channel": msg.channel,
        "external_id": msg.external_id,
    }.items() if v}
    if meta_bits:
        out["_ir_meta"] = meta_bits
    return out


def mcp_result_to_ir(tool_name: str, result: str, *, tool_call_id: str = "") -> CanonicalMessage:
    return CanonicalMessage(
        role="tool",
        blocks=[
            ContentBlock(
                BlockKind.TOOL_RESULT,
                text=str(result or ""),
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )
        ],
    )


def validate_openai_sequence(messages: list[dict[str, Any]]) -> list[str]:
    """Lightweight u/a/tool alternation checks for early failure."""
    errors: list[str] = []
    pending_tool_ids: set[str] = set()
    for i, msg in enumerate(messages):
        role = str(msg.get("role") or "")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                tid = str(tc.get("id") or "")
                if tid:
                    pending_tool_ids.add(tid)
        elif role == "tool":
            tid = str(msg.get("tool_call_id") or "")
            if tid and tid in pending_tool_ids:
                pending_tool_ids.discard(tid)
            elif tid and not pending_tool_ids:
                errors.append(f"msg[{i}]: orphan tool result id={tid}")
        elif role == "user" and pending_tool_ids:
            errors.append(
                f"msg[{i}]: user message before tool results resolved "
                f"({len(pending_tool_ids)} pending)"
            )
    if pending_tool_ids:
        errors.append(f"unresolved tool_call ids: {sorted(pending_tool_ids)[:5]}")
    return errors


def inbound_text_from_gateway(
    text: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
) -> str:
    """Optional IR normalization at gateway ingress."""
    if not message_ir_enabled():
        return text
    msg = convert_inbound(
        "wechat",
        wechat_inbound(
            text,
            platform=platform,
            external_id=str(external_id or ""),
            session_key=session_key,
        ),
    )
    return msg.primary_text() or text


def canonical_to_audit_json(msg: CanonicalMessage) -> str:
    payload = {
        "role": msg.role,
        "channel": msg.channel,
        "blocks": [
            {
                "kind": b.kind.value,
                "text": b.text[:500],
                "tool_call_id": b.tool_call_id,
                "tool_name": b.tool_name,
            }
            for b in msg.blocks
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


register_converter("wechat", lambda p: p if isinstance(p, CanonicalMessage) else wechat_inbound(str(p)))
register_converter("text", lambda p: convert_inbound("", p))
__all__ = [
    "BlockKind",
    "CanonicalMessage",
    "ContentBlock",
    "convert_inbound",
    "inbound_text_from_gateway",
    "ir_to_openai_user",
    "message_ir_enabled",
    "mcp_result_to_ir",
    "openai_message_to_ir",
    "register_converter",
    "validate_openai_sequence",
    "wechat_inbound",
]
