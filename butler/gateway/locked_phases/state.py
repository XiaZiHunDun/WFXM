from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

from butler.core.best_effort import safe_best_effort
from butler.core.loop_types import LoopCallbacks
from butler.gateway.handler_helpers import (
    _normalize_contacts_request,
    _normalize_detail_request,
    _normalize_expense_request,
    _normalize_habits_request,
    _normalize_memo_request,
    _normalize_new_session_request,
    _normalize_status_request,
    _normalize_switch_request,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class LockedTurnState:
    """Mutable carrier for one in-session turn.

    Phases mutate fields on this object. The orchestrator is
    responsible for initializing inputs and reading the final
    ``out`` after the run.
    """

    text: str
    session_key: str
    platform: str
    external_id: str | None
    loop_role: str = ""
    health: dict[str, Any] = field(default_factory=dict)
    augmented: str = ""
    ephemeral_system: Optional[str] = None
    prompt_hooks: Any = None
    loop: Any = None
    original_loop_config: Any = None
    max_out: Optional[int] = None
    run_callbacks: Any = None
    result: Any = None
    out: str = ""
    turn_started: float = 0.0
    turn_elapsed: float = 0.0
    session_read_recall_gate: bool = False
    local_project_inventory_gate: bool = False


def _load_normalizers() -> tuple[Callable[[str], Optional[str]], ...]:
    return (
        _normalize_detail_request,
        _normalize_switch_request,
        _normalize_status_request,
        _normalize_new_session_request,
        _normalize_memo_request,
        _normalize_contacts_request,
        _normalize_expense_request,
        _normalize_habits_request,
    )


def _chain_callbacks(base: Any, extra: Any) -> Any:
    if base is None:
        return extra
    if extra is None:
        return base

    def _chain(name: str) -> Any:
        fn_a = getattr(base, name, None)
        fn_b = getattr(extra, name, None)
        if fn_a is None:
            return fn_b
        if fn_b is None:
            return fn_a

        def chained(*args: Any, **kwargs: Any) -> Any:
            safe_best_effort(
                lambda: fn_a(*args, **kwargs),
                label="locked_phases.callback_chain",
            )
            return safe_best_effort(
                lambda: fn_b(*args, **kwargs),
                label="locked_phases.callback_chain",
                default=None,
            )

        return chained

    return LoopCallbacks(**{
        f.name: _chain(f.name) for f in LoopCallbacks.__dataclass_fields__.values()
    })
