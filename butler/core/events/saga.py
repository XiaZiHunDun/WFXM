"""Saga pattern for distributed transaction coordination.

Provides:
- SagaStep: Individual step with action and compensation
- SagaOrchestrator: Coordinates saga execution with automatic compensation
- build_saga: Build a saga from a list of steps
- SagaContext: Shared context for saga steps

Inspired by the Saga pattern for managing distributed transactions
without a 2PC coordinator. Each step has a compensating action
that is executed in reverse order on failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

from butler.core.effects import Result, Ok, Err

logger = logging.getLogger(__name__)

T = TypeVar("T")
E = TypeVar("E")


@dataclass
class SagaContext:
    """Shared context for saga steps.

    Allows steps to share data without tight coupling.
    Supports both sync and async execution.
    """

    _data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, data: dict[str, Any]) -> None:
        self._data.update(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data


@dataclass
class SagaStep(Generic[T]):
    """A single step in a saga.

    Attributes:
        name: Human-readable name for the step.
        action: The forward action to execute.
        compensate: The compensation action for rollback.
        compensate_on: List of exception types that trigger compensation.
        timeout: Optional timeout in seconds.
    """

    name: str
    action: Callable[["SagaContext"], Result[T, Exception]]
    compensate: Callable[["SagaContext", T], None] | None = None
    compensate_on: tuple[type[Exception], ...] = (Exception,)
    timeout: float | None = None

    def execute(self, context: SagaContext) -> Result[T, Exception]:
        """Execute the step's action."""
        try:
            result = self.action(context)
            if isinstance(result, (Ok, Err)):
                return result
            return Ok(result)
        except Exception as e:
            return Err(e)

    def compensate_step(self, context: SagaContext, result: T) -> None:
        """Execute the compensation step."""
        if self.compensate is not None:
            try:
                self.compensate(context, result)
            except Exception as e:
                logger.error(
                    "Compensation failed for step '%s': %s", self.name, e
                )


class SagaOrchestrator(Generic[T]):
    """Orchestrates saga execution with automatic compensation.

    Executes steps sequentially. If any step fails, automatically
    compensates all previously executed steps in reverse order.

    Example:
        saga = SagaOrchestrator([
            SagaStep("reserve_seat", reserve_seat, cancel_seat),
            SagaStep("process_payment", process_payment, refund_payment),
            SagaStep("send_notification", send_notification),
        ])
        result = saga.execute(SagaContext())
    """

    def __init__(self, steps: list[SagaStep[T]]) -> None:
        self._steps = steps
        self._completed_steps: list[tuple[SagaStep[T], T]] = []

    def execute(self, context: SagaContext | None = None) -> Result[T, Exception]:
        """Execute the saga, compensating on failure.

        Args:
            context: Shared context for steps. Created if not provided.

        Returns:
            Result containing the last step's success value, or an error.
        """
        if context is None:
            context = SagaContext()

        self._completed_steps = []

        for step in self._steps:
            logger.info("Saga step: %s", step.name)
            result = step.execute(context)

            if result.is_ok():
                value = result.unwrap()
                self._completed_steps.append((step, value))
            else:
                error = result.unwrap_err()
                logger.error(
                    "Saga step '%s' failed: %s. Compensating...",
                    step.name,
                    error,
                )
                self._compensate(context)
                return Err(error)

        return Ok(self._completed_steps[-1][1] if self._completed_steps else None)

    def _compensate(self, context: SagaContext) -> None:
        """Execute compensations in reverse order."""
        for step, result in reversed(self._completed_steps):
            if step.compensate is not None:
                logger.info("Compensating step: %s", step.name)
                step.compensate_step(context, result)

    @property
    def completed_count(self) -> int:
        """Number of successfully completed steps before failure."""
        return len(self._completed_steps)

    @property
    def has_failure(self) -> bool:
        """Whether the last execution failed."""
        return len(self._completed_steps) < len(self._steps)


def build_saga(
    *steps: SagaStep[T],
) -> SagaOrchestrator[T]:
    """Build a SagaOrchestrator from a list of steps.

    Args:
        *steps: Variable number of SagaStep instances.

    Returns:
        A new SagaOrchestrator.
    """
    return SagaOrchestrator(list(steps))


def create_step(
    name: str,
    action: Callable[["SagaContext"], Result[T, Exception]],
    compensate: Callable[["SagaContext", T], None] | None = None,
    compensate_on: tuple[type[Exception], ...] = (Exception,),
) -> SagaStep[T]:
    """Create a SagaStep with proper type inference.

    Args:
        name: Step name.
        action: Forward action.
        compensate: Compensation action (optional).
        compensate_on: Exception types triggering compensation.

    Returns:
        A new SagaStep.
    """
    return SagaStep(
        name=name,
        action=action,
        compensate=compensate,
        compensate_on=compensate_on,
    )


__all__ = [
    "SagaContext",
    "SagaStep",
    "SagaOrchestrator",
    "build_saga",
    "create_step",
]
