"""Dangerous terminal command patterns (Hermes approval.py subset)."""

from __future__ import annotations

import contextvars
import os
import re
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

_CURRENT_SESSION: contextvars.ContextVar[str] = contextvars.ContextVar(
    "butler_terminal_session",
    default="",
)


@dataclass(frozen=True)
class DangerCheckResult:
    allowed: bool
    reason: str = ""
    pattern: str = ""


_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("rm_rf", re.compile(r"\brm\s+(?:-\S+\s+)*\S*/", re.I)),
    ("curl_pipe_sh", re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(ba)?sh\b", re.I)),
    ("chmod_777", re.compile(r"\bchmod\s+[-+]?777\b", re.I)),
    ("disk_destroy", re.compile(r"\bmkfs\.|dd\s+if=.*of=/dev/", re.I)),
    ("reverse_shell", re.compile(r"\b(nc|netcat)\b.*(-e|--exec)\s+/bin/", re.I)),
]


def danger_patterns_enabled() -> bool:
    raw = os.getenv("BUTLER_TERMINAL_DANGER_CHECK", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def set_terminal_session_context(session_key: str) -> contextvars.Token:
    return _CURRENT_SESSION.set(str(session_key or "").strip())


def get_terminal_session_context() -> str:
    return str(_CURRENT_SESSION.get() or "").strip()


def check_dangerous_command(command: str) -> DangerCheckResult:
    if not danger_patterns_enabled():
        return DangerCheckResult(True)
    text = (command or "").strip()
    if not text:
        return DangerCheckResult(True)

    from butler.execpolicy.engine import PolicyDecision
    from butler.tools.terminal_danger_ops import (
        evaluate_execpolicy_safe,
        is_terminal_pattern_approved_safe,
    )

    pol = evaluate_execpolicy_safe(text)
    if pol is not None:
        if pol.decision == PolicyDecision.FORBIDDEN:
            msg = pol.justification or "execpolicy forbidden"
            return DangerCheckResult(False, reason=f"execpolicy: {msg}", pattern=pol.matched_rule)
        if pol.decision == PolicyDecision.ALLOW:
            return DangerCheckResult(True)
    for name, pattern in _PATTERNS:
        if pattern.search(text):
            sk = get_terminal_session_context()
            if sk and is_terminal_pattern_approved_safe(sk, name):
                return DangerCheckResult(True)
            return DangerCheckResult(
                False,
                reason=(
                    "该 terminal 命令命中危险模式，已阻断。"
                    "请拆分命令或经 Owner `/批准执行` 后重试；"
                    f"同类模式可用 `/批准模式 {name}` 本会话放行。"
                ),
                pattern=name,
            )
    return DangerCheckResult(True)
