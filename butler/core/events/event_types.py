"""Domain event types and registry for event sourcing.

Provides:
- DomainEvent base class with metadata
- EventDefinition for versioned event types
- EventRegistry for managing event definitions
- Global registry utilities
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from butler.core.effects import Result, Ok, Err

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventDefinition:
    """Definition of a domain event type with versioning support.

    Based on opencode's event definition pattern. Each event type can have
    multiple versions, and events are stored with versioned type identifiers.

    Attributes:
        type: Base event type name
        version: Schema version (default: 1)
        aggregate_field: Name of the field containing the aggregate ID
    """

    type: str
    version: int = 1
    aggregate_field: str = ""

    def versioned_type(self) -> str:
        """Return the versioned type identifier (e.g., 'SESSION_START.1')."""
        return f"{self.type}.{self.version}"


class EventRegistry:
    """Registry for event definitions with version management.

    Supports:
    - Registering event definitions
    - Looking up latest versions by type
    - Getting all durable events for persistence
    """

    def __init__(self) -> None:
        self._definitions: dict[str, EventDefinition] = {}

    def register(self, definition: EventDefinition) -> Result[None, ValueError]:
        """Register an event definition.

        Returns:
            Result[None, ValueError]: Ok(None) if registered successfully, Err(ValueError) if duplicate.
        """
        key = definition.versioned_type()
        if key in self._definitions:
            return Err(ValueError(f"Duplicate event definition: {key}"))
        self._definitions[key] = definition
        return Ok(None)

    def get(self, type: str, version: Optional[int] = None) -> Optional[EventDefinition]:
        """Get an event definition by type and optional version.

        If version is None, returns the latest version of the type.
        """
        if version is not None:
            return self._definitions.get(f"{type}.{version}")

        # Find the latest version
        latest_version = 0
        latest_def = None
        for key, def_ in self._definitions.items():
            if key.startswith(f"{type}."):
                if def_.version > latest_version:
                    latest_version = def_.version
                    latest_def = def_
        return latest_def

    def get_all(self) -> list[EventDefinition]:
        """Get all registered event definitions."""
        return list(self._definitions.values())

    def latest_definitions(self) -> dict[str, EventDefinition]:
        """Get the latest definition for each event type."""
        result: dict[str, EventDefinition] = {}
        for def_ in self._definitions.values():
            existing = result.get(def_.type)
            if existing is None or def_.version > existing.version:
                result[def_.type] = def_
        return result

    def durable_definitions(self) -> dict[str, EventDefinition]:
        """Get all durable event definitions (those with aggregate_field set)."""
        result: dict[str, EventDefinition] = {}
        for def_ in self._definitions.values():
            if def_.aggregate_field:
                key = def_.versioned_type()
                result[key] = def_
        return result


# Global event registry
_global_event_registry = EventRegistry()


def get_global_event_registry() -> EventRegistry:
    """Get the global event registry."""
    return _global_event_registry


def register_event(type: str, version: int = 1, aggregate_field: str = "") -> Result[None, ValueError]:
    """Register an event type with optional version and aggregate field."""
    return _global_event_registry.register(EventDefinition(type, version, aggregate_field))


def get_event_definition(type: str, version: Optional[int] = None) -> Optional[EventDefinition]:
    """Get an event definition from the registry."""
    return _global_event_registry.get(type, version)


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Attributes:
        event_id: Unique identifier for the event
        event_type: Type of the event
        session_key: Session identifier
        timestamp: When the event occurred (UTC)
        data: Event payload
        version: Event schema version
        metadata: Additional context
    """

    event_id: str
    event_type: str
    session_key: str
    timestamp: datetime
    data: dict[str, Any]
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dict for storage/serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_key": self.session_key,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Result["DomainEvent", Exception]:
        """Create event from dict."""
        try:
            return Ok(
                cls(
                    event_id=data["event_id"],
                    event_type=data["event_type"],
                    session_key=data["session_key"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    data=data.get("data", {}),
                    version=data.get("version", 1),
                    metadata=data.get("metadata", {}),
                )
            )
        except Exception as e:
            return Err(e)

    def __lt__(self, other: "DomainEvent") -> bool:
        """Compare by timestamp for ordering."""
        return self.timestamp < other.timestamp


def generate_event_id() -> str:
    """Generate a unique event ID."""
    import uuid

    return str(uuid.uuid4())


def now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


__all__ = [
    "DomainEvent",
    "EventDefinition",
    "EventRegistry",
    "generate_event_id",
    "now_utc",
    "get_global_event_registry",
    "register_event",
    "get_event_definition",
]
