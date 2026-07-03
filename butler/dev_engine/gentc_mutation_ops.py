"""GenTC mutation scoring best-effort helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def exec_mutant_snippet_safe(mutant_code: str, exec_fn: Callable[[str], dict[str, Any]]) -> tuple[dict[str, Any] | None, bool]:
    """Return (namespace, exec_failed). exec_failed=True means mutant killed."""
    try:
        return exec_fn(mutant_code), False
    except Exception:
        return None, True


def mutant_detected_safe(
    m_ns: dict[str, Any],
    predicates: list[tuple[str, Callable[[dict[str, Any]], bool]]],
) -> bool:
    try:
        return any(not pred(m_ns) for _, pred in predicates)
    except Exception:
        return True
