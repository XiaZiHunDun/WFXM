"""Context transform Port contracts (MOD-2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class TransformContext:
    """Per-call context for API message transforms."""

    provider: str
    model: str
    params: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] | None = None


@runtime_checkable
class ContextTransformPort(Protocol):
    """Single context transform step (lossless or lossy)."""

    @property
    def transform_id(self) -> str: ...

    @property
    def priority(self) -> int: ...

    @property
    def lossy(self) -> bool: ...

    def apply(self, messages: list[dict[str, Any]], ctx: TransformContext) -> list[dict[str, Any]]: ...
