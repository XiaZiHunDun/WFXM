"""HTTP API adapter for Butler — FastAPI-based web interface."""

from __future__ import annotations

import logging
from typing import Any

from butler.gateway.message_handler import ButlerMessageHandler

logger = logging.getLogger(__name__)

_handler: ButlerMessageHandler | None = None


def get_handler() -> ButlerMessageHandler:
    """Get or create the singleton message handler."""
    global _handler
    if _handler is None:
        _handler = ButlerMessageHandler(channel="http")
    return _handler


def handle_message(
    text: str,
    *,
    session_key: str = "default",
    platform: str = "http",
    external_id: str = "",
) -> str:
    """Process a message through the gateway handler."""
    handler = get_handler()
    return handler.handle_message(text, session_key=session_key, platform=platform, external_id=external_id)


def handle_command(
    command: str,
    *,
    session_key: str = "default",
    platform: str = "http",
    external_id: str = "",
) -> str:
    """Process a command through the gateway handler."""
    handler = get_handler()
    return handler._handle_command(command, session_key=session_key, platform=platform, external_id=external_id)