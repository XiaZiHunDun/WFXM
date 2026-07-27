"""Maybe monad for optional value handling.

Inspired by Effect-TS/ZIO and Rust's Option type.
"""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")
F = TypeVar("F")


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

    def and_then(self, f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        """Alias for bind."""
        return self.bind(f)

    def flat_map(self, f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        """Alias for bind."""
        return self.bind(f)

    def or_else(self, _f: Callable[[], Maybe[T]]) -> Maybe[T]:
        """Return self if Some, otherwise apply f."""
        return Some(self.value)

    def expect(self, _msg: str) -> T:
        """Return value if Some, raise ValueError with message if None."""
        return self.value

    def zip(self, other: Maybe[U]) -> Maybe[tuple[T, U]]:
        """Combine two Maybes into a tuple."""
        if other.is_some():
            return Some((self.value, other.value))
        return NoneVal()

    def zip_with(self, other: Maybe[U], f: Callable[[T, U], F]) -> Maybe[F]:
        """Combine two Maybes using a function."""
        if other.is_some():
            return Some(f(self.value, other.value))
        return NoneVal()

    def tap(self, f: Callable[[T], Any]) -> Maybe[T]:
        """Apply a function for side effects, return self."""
        f(self.value)
        return Some(self.value)

    def tap_none(self, _f: Callable[[], Any]) -> Maybe[T]:
        """Apply a function to None for side effects, return self."""
        return Some(self.value)

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

    def and_then(self, _f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        """Alias for bind."""
        return self.bind(_f)

    def flat_map(self, _f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        """Alias for bind."""
        return self.bind(_f)

    def or_else(self, f: Callable[[], Maybe[T]]) -> Maybe[T]:
        """Return self if Some, otherwise apply f."""
        return f()

    def expect(self, msg: str) -> T:
        """Return value if Some, raise ValueError with message if None."""
        raise ValueError(msg)

    def zip(self, other: Maybe[U]) -> Maybe[tuple[T, U]]:
        """Combine two Maybes into a tuple."""
        return NoneVal()

    def zip_with(self, other: Maybe[U], _f: Callable[[T, U], F]) -> Maybe[F]:
        """Combine two Maybes using a function."""
        return NoneVal()

    def tap(self, _f: Callable[[T], Any]) -> Maybe[T]:
        """Apply a function for side effects, return self."""
        return NoneVal()

    def tap_none(self, f: Callable[[], Any]) -> Maybe[T]:
        """Apply a function to None for side effects, return self."""
        f()
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


__all__ = [
    "Some",
    "NoneVal",
    "Maybe",
    "some",
    "none",
    "maybe_from_value",
]
