"""Per-tool call limits per agent turn (LangChain ToolCallLimitMiddleware subset)."""

from __future__ import annotations

import json
import os
from collections import defaultdict


_DEFAULT_LIMIT = 0


def per_tool_limit_enabled() -> bool:
    return per_tool_call_limit() > 0


def per_tool_call_limit() -> int:
    try:
        return max(0, int(os.getenv("BUTLER_TOOL_CALL_LIMIT_PER_TOOL", "0")))
    except ValueError:
        return _DEFAULT_LIMIT


def per_tool_limit_exempt() -> frozenset[str]:
    raw = os.getenv(
        "BUTLER_TOOL_CALL_LIMIT_EXEMPT",
        "read_file,search_files,search_code,list_directory,butler_recall",
    )
    return frozenset(t.strip() for t in raw.split(",") if t.strip())


_limiter: PerToolCallLimiter | None = None


def get_tool_call_limiter() -> PerToolCallLimiter:
    global _limiter
    if _limiter is None:
        _limiter = PerToolCallLimiter()
    return _limiter


def reset_tool_call_limiter_for_turn() -> None:
    get_tool_call_limiter().reset_for_turn()


class PerToolCallLimiter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._limit = per_tool_call_limit()

    def reset_for_turn(self) -> None:
        self._counts.clear()

    def before_call(self, tool_name: str) -> str | None:
        if not per_tool_limit_enabled():
            return None
        name = str(tool_name or "").strip()
        if not name or name in per_tool_limit_exempt():
            return None
        if self._counts[name] >= self._limit:
            return json.dumps(
                {
                    "error": f"Tool call limit reached for {name} ({self._limit} per turn)",
                    "code": "TOOL_CALL_LIMIT",
                    "tool": name,
                },
                ensure_ascii=False,
            )
        self._counts[name] += 1
        return None
