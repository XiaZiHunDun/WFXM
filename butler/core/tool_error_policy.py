"""Tool error classification: retry / replan / stop (LobeHub errorClassification subset)."""

from __future__ import annotations

import enum
import json
import os
import re
from typing import Any

from butler.env_parse import env_truthy

_POLICY_ENV = "BUTLER_TOOL_ERROR_POLICY"


class ToolErrorKind(str, enum.Enum):
    ok = "ok"
    retry = "retry"
    replan = "replan"
    stop = "stop"


_STOP_MARKERS = (
    "permission",
    "access denied",
    "not allowed",
    "blocked",
    "denied",
    "invalid api key",
    "authentication",
    "unauthorized",
    "forbidden",
    "unknown tool",
    "plan_mode",
    "security_blacklist",
    "experiment_mode",
)

_REPLAN_MARKERS = (
    "no such file",
    "file not found",
    "not found",
    "invalid argument",
    "invalid path",
    "bad escape",
    "syntax error",
    "parse error",
    "malformed",
    "missing required",
    "required field",
    "schema",
    "validation",
)

_RETRY_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "network",
    "temporarily",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
    "econnreset",
    "broken pipe",
    "resource exhausted",
)


def tool_error_policy_enabled() -> bool:
    return env_truthy(_POLICY_ENV, default=True)


def _error_text(result: str, *, exc: BaseException | None = None) -> str:
    parts: list[str] = []
    if exc is not None:
        parts.append(str(exc).lower())
    text = (result or "").strip()
    if not text:
        return " ".join(parts)
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            for key in ("error", "message", "detail", "reason"):
                val = payload.get(key)
                if val:
                    parts.append(str(val).lower())
            code = payload.get("code")
            if code:
                parts.append(str(code).lower())
    parts.append(text.lower())
    return " ".join(parts)


def _looks_like_error(result: str) -> bool:
    text = (result or "").strip()
    if not text:
        return False
    head = text[:240].lower()
    if head.startswith("error:") or head.startswith('{"error"'):
        return True
    if text.startswith("{") and '"error"' in head:
        return True
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False
    if isinstance(payload, dict) and (
        payload.get("error") or payload.get("ok") is False or payload.get("success") is False
    ):
        return True
    return False


def classify_tool_error(
    result: str,
    *,
    tool_name: str = "",
    exc: BaseException | None = None,
) -> ToolErrorKind:
    if exc is not None:
        etext = _error_text("", exc=exc)
        if any(m in etext for m in _STOP_MARKERS):
            return ToolErrorKind.stop
        if any(m in etext for m in _RETRY_MARKERS):
            return ToolErrorKind.retry
        return ToolErrorKind.replan

    if not _looks_like_error(result):
        return ToolErrorKind.ok

    blob = _error_text(result)
    code_m = re.search(r'"code"\s*:\s*"([^"]+)"', result or "", re.I)
    if code_m:
        code = code_m.group(1).lower()
        if code in (
            "permission_rule_denied",
            "plan_mode_blocked",
            "hook_blocked",
            "permission_request_hook",
            "security_blacklist",
            "tool_error_stop",
            "doom_loop",
        ):
            return ToolErrorKind.stop

    if any(m in blob for m in _STOP_MARKERS):
        return ToolErrorKind.stop
    if any(m in blob for m in _RETRY_MARKERS):
        return ToolErrorKind.retry
    if any(m in blob for m in _REPLAN_MARKERS):
        return ToolErrorKind.replan
    return ToolErrorKind.replan


def _kind_label(kind: ToolErrorKind) -> str:
    return {
        ToolErrorKind.retry: "可重试",
        ToolErrorKind.replan: "需调整",
        ToolErrorKind.stop: "应停止",
    }.get(kind, "错误")


def _next_step_hint(kind: ToolErrorKind, tool_name: str) -> str:
    if kind == ToolErrorKind.retry:
        return "稍后重试同一工具，或换网络/参数后再试"
    if kind == ToolErrorKind.replan:
        return f"请换参数、换工具或先 read_file 核对路径，勿重复相同 {tool_name or '调用'}"
    if kind == ToolErrorKind.stop:
        return "勿重复调用；向用户说明原因或请求 /批准执行 / 调整权限"
    return ""


def format_tool_error_observation(
    message: str,
    *,
    kind: ToolErrorKind,
    tool_name: str = "",
    code: str = "",
) -> str:
    """PEG-style: 错误类型 | 原因 | 建议下一步"""
    label = _kind_label(kind)
    reason = (message or "工具执行失败").strip()
    hint = _next_step_hint(kind, tool_name)
    parts = [f"错误类型: {label}", f"原因: {reason}"]
    if hint:
        parts.append(f"建议下一步: {hint}")
    if code:
        parts.append(f"code: {code}")
    return " | ".join(parts)


def apply_tool_error_policy(
    result: str,
    *,
    tool_name: str = "",
    exc: BaseException | None = None,
) -> str:
    """Annotate or reshape tool error results for the model."""
    if not tool_error_policy_enabled():
        return result

    kind = classify_tool_error(result, tool_name=tool_name, exc=exc)
    if kind == ToolErrorKind.ok:
        return result

    try:
        from butler.ops.runtime_metrics import inc

        inc("tool_error_policy", labels={"kind": kind.value, "tool": (tool_name or "?")[:32]})
    except Exception:
        pass

    msg = ""
    code = f"TOOL_ERROR_{kind.value.upper()}"
    if exc is not None:
        msg = str(exc)
    elif result.strip().startswith("{"):
        try:
            payload = json.loads(result)
            if isinstance(payload, dict):
                msg = str(payload.get("error") or payload.get("message") or result)[:500]
                code = str(payload.get("code") or code)
        except json.JSONDecodeError:
            msg = result[:500]
    else:
        msg = result[:500]

    observation = format_tool_error_observation(msg, kind=kind, tool_name=tool_name, code=code)

    if result.strip().startswith("{"):
        try:
            payload = json.loads(result)
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["error_policy"] = kind.value
                payload["error"] = observation
                payload.setdefault("code", code)
                return json.dumps(payload, ensure_ascii=False, default=str)
        except json.JSONDecodeError:
            pass

    return json.dumps(
        {
            "ok": False,
            "tool": tool_name,
            "code": code,
            "error_policy": kind.value,
            "error": observation,
        },
        ensure_ascii=False,
    )


def should_halt_loop_on_tool_error(result: str, *, tool_name: str = "") -> bool:
    if not tool_error_policy_enabled():
        return False
    return classify_tool_error(result, tool_name=tool_name) == ToolErrorKind.stop
