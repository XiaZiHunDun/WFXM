"""Minimal platform adapter base for Butler-native gateways."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional

from butler.gateway.platforms.types import MessageEvent, PlatformConfig, SendResult, SessionSource

logger = logging.getLogger(__name__)

MessageHandler = Callable[[MessageEvent], Awaitable[Optional[str]]]


class ButlerPlatformAdapter(ABC):
    """Slim adapter base: inbound event → handler → outbound send."""

    MAX_MESSAGE_LENGTH = 4000

    def __init__(self, config: PlatformConfig, platform: str) -> None:
        self.config = config
        self.platform_name = platform
        self._message_handler: MessageHandler | None = None
        self._running = False
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._fatal_error_message: str | None = None

    @property
    def name(self) -> str:
        return self.platform_name.title()

    @property
    def is_connected(self) -> bool:
        return self._running

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._message_handler = handler

    def _mark_connected(self) -> None:
        self._running = True
        self._fatal_error_message = None

    def _mark_disconnected(self) -> None:
        self._running = False

    def _set_fatal_error(self, code: str, message: str, *, retryable: bool = True) -> None:
        del code, retryable
        self._fatal_error_message = message

    def _acquire_platform_lock(self, scope: str, identity: str, label: str) -> bool:
        del scope, identity, label
        return True

    def _release_platform_lock(self) -> None:
        """No-op unless a platform overrides with real lock semantics."""

    def build_source(
        self,
        *,
        chat_id: str,
        chat_type: str,
        user_id: str,
        user_name: str = "",
    ) -> SessionSource:
        return SessionSource(
            platform=self.platform_name,
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            user_name=user_name or user_id,
        )

    async def handle_message(self, event: MessageEvent) -> None:
        """Run Butler handler and send text reply (per-chat serialized)."""
        if not self._message_handler:
            return
        if not event.source:
            return

        # Serialize per chat, not per project — one WeChat user may switch projects.
        chat_lock_key = f"{self.platform_name}:{event.source.chat_id}"
        lock = self._session_locks.setdefault(chat_lock_key, asyncio.Lock())
        async with lock:
            try:
                response = await self._message_handler(event)
                if response:
                    await self.send(event.source.chat_id, response)
            except Exception as exc:
                logger.error("[%s] handler failed: %s", self.name, exc, exc_info=True)
                try:
                    await self.send(event.source.chat_id, f"处理失败: {exc}")
                except Exception:
                    pass

    def extract_media(self, content: str) -> tuple[list[str], str]:
        return [], content if isinstance(content, str) else ""

    def extract_images(self, content: str) -> tuple[list[str], str]:
        return [], content if isinstance(content, str) else ""

    def extract_local_files(self, content: str) -> tuple[list[str], str]:
        return [], content if isinstance(content, str) else ""

    @abstractmethod
    async def connect(self) -> bool:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SendResult:
        ...
