"""Gateway base classes - unified message format and adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UnifiedMessage:
    source: str  # "cli" | "wechat" | "telegram" ...
    user_id: str
    content: str
    attachments: list[Any] = field(default_factory=list)
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAdapter(ABC):
    """Base class for gateway adapters (CLI, WeChat, Telegram, etc.)."""

    name: str = "base"

    @abstractmethod
    async def start(self) -> None:
        """Start the adapter (connect, listen, etc.)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter gracefully."""
        ...

    @abstractmethod
    async def send(self, user_id: str, content: str, **kwargs: Any) -> None:
        """Send a message back to the user."""
        ...
