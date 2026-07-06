"""Two-phase high-risk tool confirmation (OpenHands subset)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from butler.core.confirm_flags import two_phase_confirm_enabled

logger = logging.getLogger(__name__)

_HIGH_RISK_TOOLS = frozenset({
    "terminal",
    "delete_file",
    "write_file",
    "patch_file",
})

_CONFIRM_CMDS = frozenset({
    "/确认工具",
    "/confirm-tool",
    "/confirm_tool",
    "/执行待确认",
    "/run-pending-tool",
})


@dataclass(frozen=True)
class PendingToolCall:
    tool_name: str
    args: dict[str, Any]
    tool_call_id: str = ""
    fingerprint: str = ""
    requested_at: float = 0.0


def _write_confirm_enabled() -> bool:
    from butler.env_parse import env_truthy

    return bool(env_truthy("BUTLER_CONFIRM_WRITE_OPS", default=True))


def is_high_risk_tool(tool_name: str, args: dict[str, Any] | None = None) -> bool:
    name = str(tool_name or "").strip()
    if name in {"write_file", "patch_file"} and not _write_confirm_enabled():
        return False
    if name in _HIGH_RISK_TOOLS:
        return True
    if name == "terminal" and args:
        cmd = str(args.get("command") or "")
        if cmd.strip():
            from butler.core.two_phase_confirm_ops import terminal_command_blocked_safe

            blocked = terminal_command_blocked_safe(cmd)
            if blocked is True:
                return True
    return False


def _session_key(session_key: str = "") -> str:
    from butler.core.two_phase_confirm_ops import resolve_session_key_safe

    return str(resolve_session_key_safe(session_key))


def _pending_path(session_key: str) -> Path:
    import re

    from butler.config import get_butler_home

    sk = re.sub(r"[^a-zA-Z0-9._+-]+", "_", _session_key(session_key))[:120] or "default"
    path = get_butler_home() / "sessions" / sk / "pending_tool.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return cast(Path, path)


def _fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool_name, "args": args},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def load_pending(session_key: str = "") -> PendingToolCall | None:
    path = _pending_path(session_key)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("tool") or "").strip()
    if not name:
        return None
    args = raw.get("args")
    if not isinstance(args, dict):
        args = {}
    return PendingToolCall(
        tool_name=name,
        args=args,
        tool_call_id=str(raw.get("tool_call_id") or ""),
        fingerprint=str(raw.get("fingerprint") or ""),
        requested_at=float(raw.get("requested_at") or 0),
    )


def save_pending(
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str = "",
    tool_call_id: str = "",
) -> PendingToolCall:
    fp = _fingerprint(tool_name, args)
    row = PendingToolCall(
        tool_name=tool_name,
        args=dict(args),
        tool_call_id=str(tool_call_id or ""),
        fingerprint=fp,
        requested_at=time.time(),
    )
    path = _pending_path(session_key)
    path.write_text(
        json.dumps(
            {
                "tool": row.tool_name,
                "args": row.args,
                "tool_call_id": row.tool_call_id,
                "fingerprint": row.fingerprint,
                "requested_at": row.requested_at,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return row


def clear_pending(session_key: str = "") -> None:
    _pending_path(session_key).unlink(missing_ok=True)


def build_wait_message(pending: PendingToolCall) -> str:
    preview = json.dumps(pending.args, ensure_ascii=False)[:400]
    return (
        f"待确认工具：{pending.tool_name}\n"
        f"参数摘要：{preview}\n\n"
        "回复 **/确认工具** 执行；发其它内容将取消待确认并继续正常对话。"
    )


def two_phase_block_message(
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str = "",
    tool_call_id: str = "",
) -> str | None:
    """Return user-visible block message when tool must wait for Owner confirm."""
    if not two_phase_confirm_enabled():
        return None
    if not is_high_risk_tool(tool_name, args):
        return None
    sk = _session_key(session_key)
    existing = load_pending(sk)
    fp = _fingerprint(tool_name, args)
    if existing is not None and existing.fingerprint == fp:
        return build_wait_message(existing)
    pending = save_pending(tool_name, args, session_key=sk, tool_call_id=tool_call_id)
    from butler.core.two_phase_confirm_ops import record_two_phase_wait_safe

    record_two_phase_wait_safe(sk, pending.tool_name)
    return build_wait_message(pending)


def parse_confirm_command(text: str) -> bool:
    raw = (text or "").strip().lower()
    if raw in {c.lower() for c in _CONFIRM_CMDS}:
        return True
    for prefix in _CONFIRM_CMDS:
        if raw.startswith(prefix.lower()):
            return True
    return False


def cancel_pending_unless_confirm(text: str, *, session_key: str = "") -> str | None:
    """Clear stale pending tool when user sends a normal message."""
    if parse_confirm_command(text):
        return None
    if not load_pending(session_key):
        return None
    clear_pending(session_key)
    return "已取消待确认的工具调用，继续处理您本条消息。"


def try_execute_pending_confirm(
    text: str,
    *,
    session_key: str = "",
) -> str | None:
    """If *text* confirms a pending tool, run it and return the result message."""
    if not parse_confirm_command(text):
        return None
    pending = load_pending(session_key)
    if pending is None:
        return "当前没有待确认的工具调用。"
    clear_pending(session_key)
    from butler.core.two_phase_confirm_ops import dispatch_pending_tool_loud

    result, err = dispatch_pending_tool_loud(pending.tool_name, pending.args)
    if err:
        return f"执行待确认工具失败：{err}"
    preview = str(result or "")[:1500]
    return f"已执行待确认工具 `{pending.tool_name}`：\n{preview}"


__all__ = [
    "build_wait_message",
    "clear_pending",
    "is_high_risk_tool",
    "load_pending",
    "parse_confirm_command",
    "save_pending",
    "cancel_pending_unless_confirm",
    "try_execute_pending_confirm",
    "two_phase_block_message",
]
