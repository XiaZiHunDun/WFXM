"""Tool error classification: retry / replan / stop (LobeHub errorClassification subset).

This module uses Algebraic Data Types (ADT) pattern for error classification,
replacing enum + branch logic with explicit sum types and pattern matching.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, Pattern

from butler.utilities.env_parse import env_truthy

logger = logging.getLogger(__name__)

_POLICY_ENV = "BUTLER_TOOL_ERROR_POLICY"


# --- Algebraic Data Types for Tool Error Classification ---

class ToolErrorKind(ABC):
    """Base class for tool error classification ADT."""

    # Backwards compatibility class attributes
    ok: ClassVar["ToolErrorKind"]
    retry: ClassVar["ToolErrorKind"]
    replan: ClassVar["ToolErrorKind"]
    stop: ClassVar["ToolErrorKind"]

    @abstractmethod
    def label(self) -> str:
        """Return the human-readable label for this error kind."""
        ...

    @abstractmethod
    def next_step_hint(self, tool_name: str) -> str:
        """Return the suggested next step for this error kind."""
        ...

    @abstractmethod
    def should_retry(self) -> bool:
        """Return True if this error kind suggests retrying."""
        ...

    @abstractmethod
    def should_halt(self) -> bool:
        """Return True if this error kind suggests halting the loop."""
        ...

    @abstractmethod
    def should_replan(self) -> bool:
        """Return True if this error kind suggests replanning."""
        ...

    @abstractmethod
    def value(self) -> str:
        """Return the string value for serialization."""
        ...


@dataclass(frozen=True)
class Ok(ToolErrorKind):
    """Tool execution succeeded without error."""

    def label(self) -> str:
        return "成功"

    def next_step_hint(self, tool_name: str) -> str:
        return ""

    def should_retry(self) -> bool:
        return False

    def should_halt(self) -> bool:
        return False

    def should_replan(self) -> bool:
        return False

    def value(self) -> str:
        return "ok"


@dataclass(frozen=True)
class Retry(ToolErrorKind):
    """Tool execution failed but can be retried."""

    def label(self) -> str:
        return "可重试"

    def next_step_hint(self, tool_name: str) -> str:
        return "稍后重试同一工具，或换网络/参数后再试"

    def should_retry(self) -> bool:
        return True

    def should_halt(self) -> bool:
        return False

    def should_replan(self) -> bool:
        return False

    def value(self) -> str:
        return "retry"


@dataclass(frozen=True)
class Replan(ToolErrorKind):
    """Tool execution failed and requires replanning."""

    def label(self) -> str:
        return "需调整"

    def next_step_hint(self, tool_name: str) -> str:
        return f"请换参数、换工具或先 read_file 核对路径，勿重复相同 {tool_name or '调用'}"

    def should_retry(self) -> bool:
        return False

    def should_halt(self) -> bool:
        return False

    def should_replan(self) -> bool:
        return True

    def value(self) -> str:
        return "replan"


@dataclass(frozen=True)
class Stop(ToolErrorKind):
    """Tool execution failed and should halt the loop."""

    def label(self) -> str:
        return "应停止"

    def next_step_hint(self, tool_name: str) -> str:
        return "勿重复调用；向用户说明原因或请求 /批准执行 / 调整权限"

    def should_retry(self) -> bool:
        return False

    def should_halt(self) -> bool:
        return True

    def should_replan(self) -> bool:
        return False

    def value(self) -> str:
        return "stop"


# --- Classification markers ---

_STOP_MARKERS: tuple[str, ...] = (
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

_REPLAN_MARKERS: tuple[str, ...] = (
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

_RETRY_MARKERS: tuple[str, ...] = (
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

_STOP_CODES: tuple[str, ...] = (
    "permission_rule_denied",
    "plan_mode_blocked",
    "hook_blocked",
    "permission_request_hook",
    "security_blacklist",
    "tool_error_stop",
    "doom_loop",
)

_CODE_PATTERN: Pattern[str] = re.compile(r'"code"\s*:\s*"([^"]+)"', re.I)


# --- Helper functions ---

def tool_error_policy_enabled() -> bool:
    return bool(env_truthy(_POLICY_ENV, default=True))


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


# --- Classification function ---

def classify_tool_error(
    result: str,
    *,
    tool_name: str = "",
    exc: BaseException | None = None,
) -> ToolErrorKind:
    """Classify tool error using ADT pattern matching."""
    if exc is not None:
        etext = _error_text("", exc=exc)
        if any(m in etext for m in _STOP_MARKERS):
            return Stop()
        if any(m in etext for m in _RETRY_MARKERS):
            return Retry()
        return Replan()

    if not _looks_like_error(result):
        return Ok()

    blob = _error_text(result)
    code_m = _CODE_PATTERN.search(result or "")
    if code_m:
        code = code_m.group(1).lower()
        if code in _STOP_CODES:
            return Stop()

    if any(m in blob for m in _STOP_MARKERS):
        return Stop()
    if any(m in blob for m in _RETRY_MARKERS):
        return Retry()
    if any(m in blob for m in _REPLAN_MARKERS):
        return Replan()
    if "read_state" in blob or "patch_old_string" in blob:
        return Replan()
    return Replan()


# --- Formatting functions ---

def format_tool_error_observation(
    message: str,
    *,
    kind: ToolErrorKind,
    tool_name: str = "",
    code: str = "",
    hint_override: str = "",
) -> str:
    """PEG-style: 错误类型 | 原因 | 建议下一步"""
    label = kind.label()
    reason = (message or "工具执行失败").strip()
    hint = (hint_override or "").strip() or kind.next_step_hint(tool_name)
    parts = [f"错误类型: {label}", f"原因: {reason}"]
    if hint:
        parts.append(f"建议下一步: {hint}")
    if code:
        parts.append(f"code: {code}")
    return " | ".join(parts)


def _hint_from_payload(result: str) -> str:
    try:
        payload = json.loads(result or "")
    except json.JSONDecodeError:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("hint") or "").strip()
    return ""


# --- Policy application ---

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
    if isinstance(kind, Ok):
        return result

    from butler.core.tool_error_policy_ops import inc_tool_error_policy_metric_safe

    inc_tool_error_policy_metric_safe(kind=kind.value(), tool_name=tool_name or "?")
    msg = ""
    code = f"TOOL_ERROR_{kind.value().upper()}"
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

    observation = format_tool_error_observation(
        msg,
        kind=kind,
        tool_name=tool_name,
        code=code,
        hint_override=_hint_from_payload(result),
    )

    if result.strip().startswith("{"):
        try:
            payload = json.loads(result)
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["error_policy"] = kind.value()
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
            "error_policy": kind.value(),
            "error": observation,
        },
        ensure_ascii=False,
    )


def should_halt_loop_on_tool_error(result: str, *, tool_name: str = "") -> bool:
    if not tool_error_policy_enabled():
        return False
    return isinstance(classify_tool_error(result, tool_name=tool_name), Stop)


# --- Backwards compatibility ---

# Keep old enum-style attributes for backwards compatibility
ToolErrorKind.ok = Ok()
ToolErrorKind.retry = Retry()
ToolErrorKind.replan = Replan()
ToolErrorKind.stop = Stop()
