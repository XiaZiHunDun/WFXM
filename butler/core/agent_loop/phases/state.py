from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, cast

from butler.core.loop_types import LoopResult, LoopStatus, LoopTransitionReason
from butler.execution_context import get_audit_session_key
from butler.transport.reasoning_replay import store_reasoning_on_message

if TYPE_CHECKING:
    from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


def _audit_session_key(*, fallback: str = "default") -> str:
    return cast(str, get_audit_session_key(fallback=fallback))


def _store_reasoning_on_message(message: Any, reasoning: Any) -> None:
    store_reasoning_on_message(message, reasoning)


@dataclass
class TurnBodyState:
    """Mutable carrier for one turn's body execution."""

    original_config: Any = None
    budget_state: Any = None
    user_content: str = ""
    turn_tools: list[dict[str, Any]] = field(default_factory=list)
    steer_session: str = ""
    response: Optional["NormalizedResponse"] = None
    result: Optional["LoopResult"] = None

    status: LoopStatus = LoopStatus.RUNNING
    transition: LoopTransitionReason = LoopTransitionReason.UNKNOWN
    iteration: int = 0

    final_text: Optional[str] = None
    final_reasoning: Optional[str] = None


def _mark_interrupted_status(state: TurnBodyState) -> None:
    """Set state.status/transition when interrupt was detected pre-iteration."""
    state.status = LoopStatus.INTERRUPTED
    state.transition = LoopTransitionReason.INTERRUPTED
