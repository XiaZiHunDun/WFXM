"""Function combinators and utilities for Result/Maybe monads."""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, Iterable, TypeVar, cast

from butler.core.effects.result_monad import Err, Ok, Result, err, ok
from butler.core.effects.maybe_monad import Maybe, NoneVal, Some, none, some

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


# ── Pipe and Compose ──


def pipe(value: Any, *fns: Callable[[Any], Any]) -> Any:
    """Pipe a value through a sequence of functions left-to-right.

    Example:
        result = pipe(x, f, g, h)  # equivalent to h(g(f(x)))
    """
    result = value
    for fn in fns:
        result = fn(result)
    return result


def compose(*fns: Callable[..., Any]) -> Callable[..., Any]:
    """Compose functions right-to-left.

    Example:
        result = compose(h, g, f)(x)  # equivalent to h(g(f(x)))
    """

    def composed(*args: Any, **kwargs: Any) -> Any:
        if not fns:
            if args:
                return args[0]
            return None

        result = fns[-1](*args, **kwargs)
        for fn in reversed(fns[:-1]):
            result = fn(result)
        return result

    return composed


def lift_result(f: Callable[..., T]) -> Callable[..., Result[T, Exception]]:
    """Lift a function to return Result."""

    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Result[T, Exception]:
        try:
            return Ok(f(*args, **kwargs))
        except Exception as e:
            return Err(e)

    return wrapper


def lift_maybe(f: Callable[..., T | None]) -> Callable[..., Maybe[T]]:
    """Lift a function to return Maybe."""

    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Maybe[T]:
        result = f(*args, **kwargs)
        if result is None:
            return NoneVal()
        return Some(result)

    return wrapper


def collect_results(results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    """Collect a list of Results into a single Result."""
    values: list[T] = []
    for r in results:
        if r.is_err():
            return cast(Result[list[T], E], r)
        values.append(r.unwrap())
    return Ok(values)


def collect_maybes(maybes: Iterable[Maybe[T]]) -> Maybe[list[T]]:
    """Collect a list of Maybes into a single Maybe."""
    values: list[T] = []
    for m in maybes:
        if m.is_none():
            return NoneVal()
        values.append(m.unwrap())
    return Some(values)


# ── Async helpers ──


async def async_collect_results(results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    """Collect a list of async Results into a single Result."""
    values: list[T] = []
    for r in results:
        if isinstance(r, Result):
            result = r
        else:
            result = await r
        if result.is_err():
            return cast(Result[list[T], E], result)
        values.append(result.unwrap())
    return Ok(values)


async def async_collect_maybes(maybes: Iterable[Maybe[T]]) -> Maybe[list[T]]:
    """Collect a list of async Maybes into a single Maybe."""
    values: list[T] = []
    for m in maybes:
        if isinstance(m, Maybe):
            result = m
        else:
            result = await m
        if result.is_none():
            return NoneVal()
        values.append(result.unwrap())
    return Some(values)


async def async_pipe(value: Any, *fns: Callable[..., Any]) -> Any:
    """Pipe a value through a sequence of async functions left-to-right."""
    result = value
    for fn in fns:
        result = await fn(result)
    return result


# ── Function combinators ──


def identity(x: T) -> T:
    """Return the input unchanged."""
    return x


def constantly(value: T) -> Callable[..., T]:
    """Return a function that always returns the same value."""

    def constant_fn(*args: Any, **kwargs: Any) -> T:
        return value

    return constant_fn


def flip(f: Callable[[T, U], F]) -> Callable[[U, T], F]:
    """Flip the arguments of a binary function."""

    def flipped(u: U, t: T) -> F:
        return f(t, u)

    return flipped


def tap(f: Callable[[T], Any]) -> Callable[[T], T]:
    """Apply a function for side effects and return the input."""

    def tapped(x: T) -> T:
        f(x)
        return x

    return tapped


def when(condition: bool) -> Callable[[Callable[[], Any]], Callable[[], None]]:
    """Conditionally apply a function."""

    def wrapper(f: Callable[[], Any]) -> Callable[[], None]:
        def wrapped() -> None:
            if condition:
                f()

        return wrapped

    return wrapper


def unless(condition: bool) -> Callable[[Callable[[], Any]], Callable[[], None]]:
    """Conditionally apply a function if condition is false."""

    def wrapper(f: Callable[[], Any]) -> Callable[[], None]:
        def wrapped() -> None:
            if not condition:
                f()

        return wrapped

    return wrapper


# ── Result/Maybe transformations ──


def result_to_maybe(result: Result[T, E]) -> Maybe[T]:
    """Convert Result to Maybe, discarding error."""
    if result.is_ok():
        return Some(result.unwrap())
    return NoneVal()


def maybe_to_result(maybe: Maybe[T], error: E) -> Result[T, E]:
    """Convert Maybe to Result, using provided error for None."""
    if maybe.is_some():
        return Ok(maybe.unwrap())
    return Err(error)


def option_to_result(value: T | None, error: E) -> Result[T, E]:
    """Convert optional value to Result."""
    if value is None:
        return Err(error)
    return Ok(value)


# ── Filter and find ──


def filter_map(maybes: Iterable[Maybe[T]]) -> list[T]:
    """Filter out None values and unwrap Some values."""
    return [m.unwrap() for m in maybes if m.is_some()]


def find_map(values: Iterable[T], f: Callable[[T], Maybe[U]]) -> Maybe[U]:
    """Apply f to each value, return first Some result."""
    for value in values:
        result = f(value)
        if result.is_some():
            return result
    return NoneVal()


def partition_results(results: Iterable[Result[T, E]]) -> tuple[list[T], list[E]]:
    """Partition Results into Ok values and Err values."""
    ok_values: list[T] = []
    err_values: list[E] = []
    for r in results:
        if r.is_ok():
            ok_values.append(r.unwrap())
        else:
            err_values.append(r.unwrap_err())
    return ok_values, err_values


def partition_maybes(maybes: Iterable[Maybe[T]]) -> tuple[list[T], list[None]]:
    """Partition Maybes into Some values and None values."""
    some_values: list[T] = []
    none_values: list[None] = []
    for m in maybes:
        if m.is_some():
            some_values.append(m.unwrap())
        else:
            none_values.append(None)
    return some_values, none_values


# ── Traverse and sequence ──


def traverse_result(
    values: Iterable[T], f: Callable[[T], Result[U, E]]
) -> Result[list[U], E]:
    """Apply a Result-returning function to each value and collect results."""
    return collect_results(f(v) for v in values)


def traverse_maybe(values: Iterable[T], f: Callable[[T], Maybe[U]]) -> Maybe[list[U]]:
    """Apply a Maybe-returning function to each value and collect results."""
    return collect_maybes(f(v) for v in values)


async def async_traverse_result(
    values: Iterable[T], f: Callable[[T], Any]
) -> Result[list[U], E]:
    """Apply an async Result-returning function to each value."""
    tasks = [f(v) for v in values]
    results = await asyncio.gather(*tasks)
    return collect_results(results)


async def async_traverse_maybe(
    values: Iterable[T], f: Callable[[T], Any]
) -> Maybe[list[U]]:
    """Apply an async Maybe-returning function to each value."""
    tasks = [f(v) for v in values]
    results = await asyncio.gather(*tasks)
    return collect_maybes(results)


def sequence_results(results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    """Convert a list of Results into a Result of lists."""
    return collect_results(results)


def sequence_maybes(maybes: Iterable[Maybe[T]]) -> Maybe[list[T]]:
    """Convert a list of Maybes into a Maybe of lists."""
    return collect_maybes(maybes)


# ── Result-specific utilities ──


def map_error(result: Result[T, E], f: Callable[[E], F]) -> Result[T, F]:
    """Map over the error of a Result."""
    if result.is_err():
        return Err(f(result.unwrap_err()))
    return cast(Result[T, F], result)


def recover(result: Result[T, E], f: Callable[[E], T]) -> T:
    """Recover from an error by applying a function."""
    if result.is_err():
        return f(result.unwrap_err())
    return result.unwrap()


def ensure(result: Result[T, E], condition: Callable[[T], bool], error: F) -> Result[T, F]:
    """Ensure a condition is met, otherwise return error."""
    if result.is_ok():
        value = result.unwrap()
        if condition(value):
            return cast(Result[T, F], Ok(value))
        return Err(error)
    return cast(Result[T, F], result)


# ── Maybe-specific utilities ──


def with_default(maybe: Maybe[T], default: T) -> T:
    """Return the value if Some, otherwise return default."""
    return maybe.unwrap_or(default)


def get_or_else(maybe: Maybe[T], f: Callable[[], T]) -> T:
    """Return the value if Some, otherwise apply f."""
    return maybe.unwrap_or_else(f)


def flatten(maybe: Maybe[Maybe[T]]) -> Maybe[T]:
    """Flatten a nested Maybe."""
    if maybe.is_some():
        return maybe.unwrap()
    return NoneVal()


def flatten_result(result: Result[Result[T, E], E]) -> Result[T, E]:
    """Flatten a nested Result."""
    if result.is_ok():
        return result.unwrap()
    return cast(Result[T, E], result)


__all__ = [
    "pipe",
    "compose",
    "lift_result",
    "lift_maybe",
    "collect_results",
    "collect_maybes",
    # Async helpers
    "async_collect_results",
    "async_collect_maybes",
    "async_pipe",
    # Function combinators
    "identity",
    "constantly",
    "flip",
    "tap",
    "when",
    "unless",
    # Transformations
    "result_to_maybe",
    "maybe_to_result",
    "option_to_result",
    # Filter and find
    "filter_map",
    "find_map",
    "partition_results",
    "partition_maybes",
    # Traverse and sequence
    "traverse_result",
    "traverse_maybe",
    "async_traverse_result",
    "async_traverse_maybe",
    "sequence_results",
    "sequence_maybes",
    # Result utilities
    "map_error",
    "recover",
    "ensure",
    # Maybe utilities
    "with_default",
    "get_or_else",
    "flatten",
    "flatten_result",
]
