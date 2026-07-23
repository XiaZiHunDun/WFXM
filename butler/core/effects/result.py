"""Result and Maybe monads for functional error handling.

Inspired by Effect-TS/ZIO and Rust's Result type.
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Generic, Iterable, TypeVar, cast

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


class Ok(Generic[T, E]):
    """Success variant of Result."""

    __match_args__ = ("value",)

    def __init__(self, value: T) -> None:
        self.value = value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, _default: T) -> T:
        return self.value

    def unwrap_or_else(self, _f: Callable[[E], T]) -> T:
        return self.value

    def map(self, f: Callable[[T], U]) -> Result[U, E]:
        return Ok(f(self.value))

    def map_err(self, _f: Callable[[E], Any]) -> Result[T, E]:
        return Ok(self.value)

    def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return f(self.value)

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Ok):
            return self.value == other.value
        return False


class Err(Generic[T, E]):
    """Error variant of Result."""

    __match_args__ = ("error",)

    def __init__(self, error: E) -> None:
        self.error = error

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> T:
        raise ValueError(f"Cannot unwrap Err: {self.error}")

    def unwrap_or(self, default: T) -> T:
        return default

    def unwrap_or_else(self, f: Callable[[E], T]) -> T:
        return f(self.error)

    def map(self, _f: Callable[[T], U]) -> Result[U, E]:
        return Err(self.error)

    def map_err(self, f: Callable[[E], Any]) -> Result[T, Any]:
        return Err(f(self.error))

    def bind(self, _f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return Err(self.error)

    def __repr__(self) -> str:
        return f"Err({self.error!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Err):
            return self.error == other.error
        return False


Result = Ok[T, E] | Err[T, E]


def ok(value: T) -> Ok[T, Any]:
    """Create an Ok result."""
    return Ok(value)


def err(error: E) -> Err[Any, E]:
    """Create an Err result."""
    return Err(error)


def result_from_fn(
    f: Callable[[], T],
    *,
    catch: type[Exception] | tuple[type[Exception], ...] = Exception,
) -> Result[T, Exception]:
    """Execute a function and wrap result in Result."""
    try:
        return Ok(f())
    except catch as e:
        return Err(e)


async def async_result_from_fn(
    f: Callable[[], Any],
    *,
    catch: type[Exception] | tuple[type[Exception], ...] = Exception,
) -> Result[Any, Exception]:
    """Execute an async function and wrap result in Result."""
    try:
        return Ok(await f())
    except catch as e:
        return Err(e)


# ── Maybe monad ──


class Some(Generic[T]):
    """Some variant of Maybe."""

    __match_args__ = ("value",)

    def __init__(self, value: T) -> None:
        self.value = value

    def is_some(self) -> bool:
        return True

    def is_none(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, _default: T) -> T:
        return self.value

    def unwrap_or_else(self, _f: Callable[[], T]) -> T:
        return self.value

    def map(self, f: Callable[[T], U]) -> Maybe[U]:
        return Some(f(self.value))

    def bind(self, f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        return f(self.value)

    def __repr__(self) -> str:
        return f"Some({self.value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Some):
            return self.value == other.value
        return False


class NoneVal(Generic[T]):
    """None variant of Maybe."""

    def is_some(self) -> bool:
        return False

    def is_none(self) -> bool:
        return True

    def unwrap(self) -> T:
        raise ValueError("Cannot unwrap None")

    def unwrap_or(self, default: T) -> T:
        return default

    def unwrap_or_else(self, f: Callable[[], T]) -> T:
        return f()

    def map(self, _f: Callable[[T], U]) -> Maybe[U]:
        return NoneVal()

    def bind(self, _f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        return NoneVal()

    def __repr__(self) -> str:
        return "NoneVal()"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, NoneVal)


Maybe = Some[T] | NoneVal[T]


def some(value: T) -> Some[T]:
    """Create a Some value."""
    return Some(value)


def none() -> NoneVal[Any]:
    """Create a None value."""
    return NoneVal()


def maybe_from_value(value: T | None) -> Maybe[T]:
    """Convert optional value to Maybe."""
    if value is None:
        return NoneVal()
    return Some(value)


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


__all__ = [
    "Ok",
    "Err",
    "Result",
    "ok",
    "err",
    "result_from_fn",
    "async_result_from_fn",
    "Some",
    "NoneVal",
    "Maybe",
    "some",
    "none",
    "maybe_from_value",
    "pipe",
    "compose",
    "lift_result",
    "lift_maybe",
    "collect_results",
    "collect_maybes",
]
