"""Advanced Effect combinators for functional programming.

Provides:
- Lazy: Lazily-evaluated values for deferred computation
- match_result/match_maybe: Pattern matching with dict-style handlers
- partition_either: Split Results into separate lists
- result_from_optional: Convert optional values to Result
- while_some: Iterate while a Maybe returns Some
- deep_map/deep_sequence: Nested Result/Maybe traversal
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Generic, Iterable, TypeVar

from butler.core.effects.result_monad import Err, Ok, Result
from butler.core.effects.maybe_monad import Maybe, Some

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


class Lazy(Generic[T]):
    """Lazily-evaluated value for deferred computation.

    Useful for expensive computations that should only be evaluated
    when needed, or for building recursive data structures.

    Example:
        lazy_val = Lazy(lambda: expensive_computation())
        # expensive_computation is not called yet
        value = lazy_val.evaluate()  # called here
    """

    def __init__(self, fn: Callable[[], T]) -> None:
        self._fn = fn
        self._value: T | None = None
        self._evaluated = False

    def evaluate(self) -> T:
        """Evaluate the lazy value, caching the result."""
        if not self._evaluated:
            self._value = self._fn()
            self._evaluated = True
        return self._value  # type: ignore[return-value]

    @property
    def is_evaluated(self) -> bool:
        """Whether the lazy value has been evaluated."""
        return self._evaluated

    def map(self, f: Callable[[T], U]) -> "Lazy[U]":
        """Map over the lazy value without evaluating."""
        return Lazy(lambda: f(self.evaluate()))

    def flat_map(self, f: Callable[[T], "Lazy[U]"]) -> "Lazy[U]":
        """Flat map over the lazy value."""
        return Lazy(lambda: f(self.evaluate()).evaluate())

    def __repr__(self) -> str:
        if self._evaluated:
            return f"Lazy({self._value!r})"
        return "Lazy(<unevaluated>)"

    def __bool__(self) -> bool:
        return bool(self.evaluate())


def match_result(
    result: Result[T, E],
    *,
    ok: Callable[[T], U] | None = None,
    err: Callable[[E], F] | None = None,
    default_ok: U | None = None,
    default_err: F | None = None,
) -> Any:
    """Pattern match on a Result with optional handlers.

    Applies the matching handler if provided, otherwise returns the
    corresponding default. Raises ValueError if no handler or default
    is provided for the matching variant.

    Args:
        result: The Result to match on.
        ok: Handler for Ok variant.
        err: Handler for Err variant.
        default_ok: Default value if ok handler not provided.
        default_err: Default value if err handler not provided.

    Returns:
        The result of the matching handler or default.
    """
    if result.is_ok():
        if ok is not None:
            return ok(result.unwrap())
        if default_ok is not None:
            return default_ok
        raise ValueError("No handler or default for Ok variant")
    else:
        if err is not None:
            return err(result.unwrap_err())
        if default_err is not None:
            return default_err
        raise ValueError("No handler or default for Err variant")


def match_maybe(
    maybe: Maybe[T],
    *,
    some: Callable[[T], U] | None = None,
    none_fn: Callable[[], F] | None = None,
    default_some: U | None = None,
    default_none: F | None = None,
) -> Any:
    """Pattern match on a Maybe with optional handlers.

    Args:
        maybe: The Maybe to match on.
        some: Handler for Some variant.
        none_fn: Handler for None variant.
        default_some: Default value if some handler not provided.
        default_none: Default value if none handler not provided.

    Returns:
        The result of the matching handler or default.
    """
    if maybe.is_some():
        if some is not None:
            return some(maybe.unwrap())
        if default_some is not None:
            return default_some
        raise ValueError("No handler or default for Some variant")
    else:
        if none_fn is not None:
            return none_fn()
        if default_none is not None:
            return default_none
        raise ValueError("No handler or default for None variant")


def partition_either(
    results: Iterable[Result[T, E]],
) -> tuple[list[T], list[E]]:
    """Partition an iterable of Results into Ok values and Err values.

    Unlike partition_results which collects, this partitions while
    consuming the iterator.

    Args:
        results: Iterable of Result values.

    Returns:
        Tuple of (ok_values, err_values).
    """
    ok_values: list[T] = []
    err_values: list[E] = []
    for r in results:
        if r.is_ok():
            ok_values.append(r.unwrap())
        else:
            err_values.append(r.unwrap_err())
    return ok_values, err_values


def result_from_optional(value: T | None, error: E) -> Result[T, E]:
    """Convert an optional value to a Result.

    Args:
        value: Optional value.
        error: Error to use if value is None.

    Returns:
        Ok(value) if value is not None, Err(error) otherwise.
    """
    if value is None:
        return Err(error)
    return Ok(value)


def while_some(
    initial: T,
    f: Callable[[T], Maybe[T]],
    max_iterations: int = 1000,
) -> list[T]:
    """Iterate while f returns Some, collecting all values.

    Useful for loops that produce optional next values, such as
    pagination or tree traversal.

    Args:
        initial: Starting value.
        f: Function that returns Maybe[T] for each iteration.
        max_iterations: Maximum number of iterations to prevent infinite loops.

    Returns:
        List of all values produced by f.
    """
    values: list[T] = []
    current: Maybe[T] = Some(initial)
    iterations = 0

    while current.is_some() and iterations < max_iterations:
        value = current.unwrap()
        values.append(value)
        current = f(value)
        iterations += 1

    return values


def deep_map(
    result: Result[T, E],
    f: Callable[[T], U],
    *,
    transform_error: Callable[[E], F] | None = None,
) -> Result[U, F]:
    """Map over a Result, optionally transforming the error type too.

    Args:
        result: The Result to map.
        f: Function to apply to the Ok value.
        transform_error: Optional function to transform the error type.

    Returns:
        New Result with mapped Ok value and optionally mapped error.
    """
    if result.is_ok():
        return Ok(f(result.unwrap()))
    else:
        error = result.unwrap_err()
        if transform_error is not None:
            return Err(transform_error(error))
        return Err(error)  # type: ignore[return-value]


async def deep_sequence(
    results: Iterable[Any],
) -> Result[list[T], E]:
    """Sequence an iterable of Results or async Results.

    Handles mixed sync/async Results.

    Args:
        results: Iterable of Results or futures of Results.

    Returns:
        A Result containing a list of all Ok values, or the first Err.
    """
    values: list[T] = []
    for r in results:
        result = await r if asyncio.isfuture(r) else r
        if not isinstance(result, (Ok, Err)):
            result = await result
        if result.is_err():
            return result  # type: ignore[return-value]
        values.append(result.unwrap())
    return Ok(values)


__all__ = [
    "Lazy",
    "match_result",
    "match_maybe",
    "partition_either",
    "result_from_optional",
    "while_some",
    "deep_map",
    "deep_sequence",
]
