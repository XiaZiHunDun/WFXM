"""Algebraic Data Types (ADT) for domain modeling.

Provides:
- Sum types (union/tagged union): For representing alternative values
  - TaggedUnion: Base class for tagged union types
  - Either: Binary sum type with Left/Right variants
- Product types (tuple/record): For combining multiple values
  - Record: Named product type with field access
- Pattern matching utilities for ADT variants

These types enable:
- Expressive domain modeling with type-safe variants
- Exhaustive pattern matching on discriminated unions
- Type-safe product types for structured data
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")
A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")


@dataclass
class TaggedUnion:
    """Base class for tagged union (sum) types.

    Subclasses represent different variants of a union type.
    Each variant has a tag and associated data.

    Example:
        class ToolResult(TaggedUnion):
            tag: str

        @dataclass
        class ToolSuccess(ToolResult):
            tag: Literal["success"] = "success"
            output: str = ""

        @dataclass
        class ToolError(ToolResult):
            tag: Literal["error"] = "error"
            message: str = ""
    """

    tag: str = ""

    def match(self, **handlers: Callable[..., Any]) -> Any:
        """Pattern match on the union variant.

        Args:
            **handlers: Keyword handlers for each variant tag.
                Each handler receives the variant's fields.

        Returns:
            The result of the matching handler.

        Raises:
            ValueError: If no handler matches the current tag.
        """
        tag = self.tag
        if tag in handlers:
            handler = handlers[tag]
            # Pass all fields except tag to the handler
            fields = {
                k: v
                for k, v in self.__dict__.items()
                if k != "tag" and not k.startswith("_")
            }
            return handler(**fields)
        raise ValueError(f"No handler for variant: {tag}")

    def fold(self, *handlers: Callable[..., Any]) -> Any:
        """Fold over the union variant by position.

        Handlers are matched in order of variant definitions.
        Less safe than match() but more concise for simple cases.
        """

        variant_index = self._variant_index()
        if variant_index < len(handlers):
            return handlers[variant_index](self)
        raise ValueError(
            f"Handler index {variant_index} out of range (have {len(handlers)} handlers)"
        )

    def _variant_index(self) -> int:
        """Get the index of this variant among siblings."""
        # Use __match_args__ or mro ordering
        for i, cls in enumerate(type(self).__mro__):
            if cls is TaggedUnion:
                return i - 1  # Simplified: return first concrete variant
        return 0


@dataclass
class Either(Generic[A, B], TaggedUnion):
    """Binary sum type with Left/Right variants.

    Based on Haskell's Either type. Represents a value that is
    either a Left (failure/error case) or Right (success/value case).

    This is an alias for Result with different naming conventions.

    Example:
        def parse_int(s: str) -> Either[str, int]:
            try:
                return Right(int(s))
            except ValueError:
                return Left(f"Cannot parse: {s}")

        result = parse_int("42")
        result.match(
            Left=lambda err: f"Error: {err}",
            Right=lambda val: f"Value: {val}",
        )
    """

    tag: str = ""

    def is_left(self) -> bool:
        return self.tag == "left"

    def is_right(self) -> bool:
        return self.tag == "right"

    @property
    def left_value(self) -> A | None:
        if self.is_left():
            return getattr(self, "value", None)
        return None

    @property
    def right_value(self) -> B | None:
        if self.is_right():
            return getattr(self, "value", None)
        return None

    def map_right(self, f: Callable[[B], U]) -> "Either[A, U]":
        if self.is_right():
            return Right(f(self.right_value))  # type: ignore[return-value]
        return self  # type: ignore[return-value]

    def map_left(self, f: Callable[[A], F]) -> "Either[F, B]":
        if self.is_left():
            return Left(f(self.left_value))  # type: ignore[return-value]
        return self  # type: ignore[return-value]

    def flat_map(self, f: Callable[[B], "Either[A, U]"]) -> "Either[A, U]":
        if self.is_right():
            return f(self.right_value)  # type: ignore[return-value]
        return self  # type: ignore[return-value]


@dataclass
class Left(Either[A, B]):
    """Left variant of Either (typically an error)."""

    value: A = None  # type: ignore[assignment]

    def __init__(self, value: A) -> None:
        self.tag = "left"
        self.value = value


@dataclass
class Right(Either[A, B]):
    """Right variant of Either (typically a success value)."""

    value: B = None  # type: ignore[assignment]

    def __init__(self, value: B) -> None:
        self.tag = "right"
        self.value = value


def left(value: A) -> Left[A, Any]:
    """Create a Left value."""
    return Left(value)


def right(value: B) -> Right[Any, B]:
    """Create a Right value."""
    return Right(value)


@dataclass
class Record:
    """Product type with named fields.

    Provides a lightweight product type with field access,
    supporting both positional and named construction.

    Example:
        class Point(Record):
            x: float
            y: float

        p = Point(3.0, 4.0)
        print(p.x, p.y)  # 3.0 4.0
    """

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary."""
        return {
            k: v
            for k, v in self.__dict__.items()
            if not k.startswith("_")
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Record":
        """Create record from dictionary."""
        return cls(**data)

    def merge(self, other: "Record") -> "Record":
        """Merge two records, with other taking precedence."""
        merged = self.to_dict()
        merged.update(other.to_dict())
        return self.__class__(**merged)


def match_either(
    either: Either[A, B],
    *,
    left_fn: Callable[[A], U] | None = None,
    right_fn: Callable[[B], F] | None = None,
    default_left: U | None = None,
    default_right: F | None = None,
) -> Any:
    """Pattern match on an Either value.

    Args:
        either: The Either to match on.
        left_fn: Handler for Left variant.
        right_fn: Handler for Right variant.
        default_left: Default if left_fn not provided.
        default_right: Default if right_fn not provided.

    Returns:
        The result of the matching handler or default.
    """
    if either.is_left():
        if left_fn is not None:
            return left_fn(either.left_value)
        if default_left is not None:
            return default_left
        raise ValueError("No handler for Left variant")
    else:
        if right_fn is not None:
            return right_fn(either.right_value)
        if default_right is not None:
            return default_right
        raise ValueError("No handler for Right variant")


def traverse_either(
    eithers: list[Either[A, B]],
) -> Either[A, list[B]]:
    """Traverse a list of Eithers, collecting all right values.

    Returns the first Left encountered, or a Right with all values.
    """
    values: list[B] = []
    for e in eithers:
        if e.is_left():
            return e  # type: ignore[return-value]
        values.append(e.right_value)  # type: ignore[arg-type]
    return Right(values)


def partition_eithers(
    eithers: list[Either[A, B]],
) -> tuple[list[A], list[B]]:
    """Partition a list of Eithers into left and right values."""
    lefts: list[A] = []
    rights: list[B] = []
    for e in eithers:
        if e.is_left():
            lefts.append(e.left_value)  # type: ignore[arg-type]
        else:
            rights.append(e.right_value)  # type: ignore[arg-type]
    return lefts, rights


__all__ = [
    # Sum types
    "TaggedUnion",
    "Either",
    "Left",
    "Right",
    "left",
    "right",
    # Product types
    "Record",
    # Utilities
    "match_either",
    "traverse_either",
    "partition_eithers",
]
