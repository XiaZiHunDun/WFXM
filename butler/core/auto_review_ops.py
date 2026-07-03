"""Auto-review best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import re
from typing import Any

from butler.core.best_effort import safe_best_effort

_READ_ONLY_HINTS = re.compile(
    r"(?i)\b(git\s+(status|diff|log|show|branch)|pytest\s+--collect|ls\b|pwd\b|cat\s+|head\s+|tail\s+|wc\s+)",
)


def sandbox_read_only_auto_review_safe(
    command: str,
    *,
    diagnostics: dict[str, Any] | None,
) -> bool:
    def _run() -> bool:
        from butler.tools.terminal_sandbox import terminal_sandbox_enabled

        if not terminal_sandbox_enabled() or not _READ_ONLY_HINTS.search(command):
            raise ValueError("sandbox shortcut not applicable")
        if isinstance(diagnostics, dict):
            diagnostics["auto_review_allowed"] = True
        return True

    result = safe_best_effort(
        _run,
        label="auto_review.sandbox_shortcut",
        default=False,
    )
    return bool(result)


def run_auto_review_llm_safe(
    command: str,
    *,
    diagnostics: dict[str, Any] | None,
) -> tuple[bool, str] | None:
    def _run() -> tuple[bool, str]:
        from butler.transport.auxiliary_client import auxiliary_complete

        prompt = (
            "You are a security reviewer. Reply ONLY with JSON "
            '{"allow":true|false,"reason":"..."}. '
            "Allow ONLY read-only inspection commands. "
            f"Command: {command[:500]}"
        )
        raw = auxiliary_complete(
            prompt,
            task="auto_review",
            system="You are a security reviewer. Reply only with JSON.",
        )
        parsed = parse_auto_review_llm_response_safe(raw, diagnostics=diagnostics)
        if parsed is None:
            raise ValueError("reviewer denied or parse failed")
        return parsed

    result = safe_best_effort(
        _run,
        label="auto_review.llm_call",
        default=None,
    )
    if isinstance(result, tuple) and len(result) == 2:
        allowed, reason = result
        return bool(allowed), str(reason)
    return None


def parse_auto_review_llm_response_safe(
    raw: Any,
    *,
    diagnostics: dict[str, Any] | None,
) -> tuple[bool, str] | None:
    def _run() -> tuple[bool, str]:
        body = str(raw or "").strip()
        if "{" in body:
            body = body[body.index("{") : body.rindex("}") + 1]
        data = json.loads(body)
        if not isinstance(data, dict) or data.get("allow") is not True:
            raise ValueError("reviewer denied")
        if isinstance(diagnostics, dict):
            diagnostics["auto_review_allowed"] = True
        return True, str(data.get("reason") or "ok")

    result = safe_best_effort(
        _run,
        label="auto_review.llm_response",
        default=None,
    )
    if isinstance(result, tuple) and len(result) == 2:
        allowed, reason = result
        return bool(allowed), str(reason)
    return None
