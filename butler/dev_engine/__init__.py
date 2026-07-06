"""Butler v4 L4 Development Engine — 内置开发引擎.

Provides structured development loop (PLAN→LOCATE→EDIT→VERIFY→FIX),
edit algebra with rollback, multi-strategy code search,
layered verification, and diagnostic-driven fix strategies.

Theory: docs/architecture/v4-dev-engine-theory.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from butler.dev_engine.dev_state import DevState

__all__ = [
    "create_dev_state",
    "dev_engine_enabled",
    "register_dev_engine_tools",
]


def create_dev_state(task_description: str = "") -> DevState:
    from butler.dev_engine.dev_loop import create_dev_state as _create

    return _create(task_description=task_description)


def dev_engine_enabled() -> bool:
    from butler.dev_engine.dev_tools import dev_engine_enabled as _enabled

    return bool(_enabled())


def register_dev_engine_tools(register_fn: Callable[..., None]) -> None:
    from butler.dev_engine.dev_tools import register_dev_engine_tools as _register

    _register(register_fn)
