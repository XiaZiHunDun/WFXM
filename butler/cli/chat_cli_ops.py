"""Chat CLI turn execution helpers (P0-A)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any


def run_exec_turn_safe(run_turn: Callable[[], Any]) -> int:
    try:
        result = run_turn()
        return 0 if result.status.value == "completed" else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run_interactive_turn_safe(
    run_turn: Callable[[], Any],
    *,
    on_keyboard_interrupt: Callable[[], Any],
    on_error: Callable[[BaseException], Any],
) -> Any:
    try:
        return run_turn()
    except KeyboardInterrupt:
        return on_keyboard_interrupt()
    except Exception as exc:
        return on_error(exc)
