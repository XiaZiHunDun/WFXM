"""Result monad for functional error handling.

Inspired by Effect-TS/ZIO and Rust's Result type.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar, cast

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


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

    def and_then(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Alias for bind."""
        return self.bind(f)

    def flat_map(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Alias for bind."""
        return self.bind(f)

    def or_else(self, _f: Callable[[E], Result[T, F]]) -> Result[T, F]:
        """Return self if Ok, otherwise apply f to error."""
        return cast(Result[T, F], Ok(self.value))

    def unwrap_err(self) -> E:
        """Return the error value if Err, raises ValueError if Ok."""
        raise ValueError("Cannot unwrap_err Ok")

    def expect(self, _msg: str) -> T:
        """Return value if Ok, raise ValueError with message if Err."""
        return self.value

    def expect_err(self, msg: str) -> E:
        """Return error if Err, raise ValueError with message if Ok."""
        raise ValueError(msg)

    def zip(self, other: Result[U, E]) -> Result[tuple[T, U], E]:
        """Combine two Results into a tuple."""
        if other.is_ok():
            return Ok((self.value, other.value))
        return cast(Result[tuple[T, U], E], other)

    def zip_with(self, other: Result[U, E], f: Callable[[T, U], F]) -> Result[F, E]:
        """Combine two Results using a function."""
        if other.is_ok():
            return Ok(f(self.value, other.value))
        return cast(Result[F, E], other)

    def tap(self, f: Callable[[T], Any]) -> Result[T, E]:
        """Apply a function for side effects, return self."""
        f(self.value)
        return Ok(self.value)

    def tap_err(self, _f: Callable[[E], Any]) -> Result[T, E]:
        """Apply a function to error for side effects, return self."""
        return Ok(self.value)

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Ok):
            return self.value == other.value
        return False

    def fold(self, on_ok: Callable[[T], U], on_err: Callable[[E], U]) -> U:
        """Collapse the Result into a single value by applying the appropriate function."""
        return on_ok(self.value)

    def match(self, ok_fn: Callable[[T], U], err_fn: Callable[[E], U]) -> U:
        """Pattern match on the Result variant."""
        return ok_fn(self.value)

    def to_value(self) -> T:
        """Extract the value directly."""
        return self.value


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

    def and_then(self, _f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Alias for bind."""
        return self.bind(_f)

    def flat_map(self, _f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        """Alias for bind."""
        return self.bind(_f)

    def or_else(self, f: Callable[[E], Result[T, F]]) -> Result[T, F]:
        """Return self if Ok, otherwise apply f to error."""
        return f(self.error)

    def unwrap_err(self) -> E:
        """Return the error value if Err, raises ValueError if Ok."""
        return self.error

    def expect(self, msg: str) -> T:
        """Return value if Ok, raise ValueError with message if Err."""
        raise ValueError(f"{msg}: {self.error}")

    def expect_err(self, _msg: str) -> E:
        """Return error if Err, raise ValueError with message if Ok."""
        return self.error

    def zip(self, other: Result[U, E]) -> Result[tuple[T, U], E]:
        """Combine two Results into a tuple."""
        return cast(Result[tuple[T, U], E], Err(self.error))

    def zip_with(self, other: Result[U, E], _f: Callable[[T, U], F]) -> Result[F, E]:
        """Combine two Results using a function."""
        return cast(Result[F, E], Err(self.error))

    def tap(self, _f: Callable[[T], Any]) -> Result[T, E]:
        """Apply a function for side effects, return self."""
        return Err(self.error)

    def tap_err(self, f: Callable[[E], Any]) -> Result[T, E]:
        """Apply a function to error for side effects, return self."""
        f(self.error)
        return Err(self.error)

    def __repr__(self) -> str:
        return f"Err({self.error!r})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Err):
            return self.error == other.error
        return False

    def fold(self, on_ok: Callable[[T], U], on_err: Callable[[E], U]) -> U:
        """Collapse the Result into a single value by applying the appropriate function."""
        return on_err(self.error)

    def match(self, ok_fn: Callable[[T], U], err_fn: Callable[[E], U]) -> U:
        """Pattern match on the Result variant."""
        return err_fn(self.error)

    def to_value(self) -> T:
        """Extract the value. Raises ValueError for Err."""
        raise ValueError(f"Cannot extract value from Err: {self.error}")


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


__all__ = [
    "Ok",
    "Err",
    "Result",
    "ok",
    "err",
    "result_from_fn",
    "async_result_from_fn",
]
