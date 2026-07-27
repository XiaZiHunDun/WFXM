"""HTTP platform adapter for Butler — FastAPI-based web interface."""

from __future__ import annotations

from .adapter import get_handler, handle_command, handle_message
from .routes import register_routes

__all__ = [
    "get_handler",
    "handle_command",
    "handle_message",
    "register_routes",
]