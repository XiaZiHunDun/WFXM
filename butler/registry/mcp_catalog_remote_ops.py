"""Remote MCP catalog fetch best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def fetch_catalog_payload_safe(url: str, *, text: str) -> Any | None:
    try:
        if url.lower().endswith((".yaml", ".yml")):
            return yaml.safe_load(text)
        import json

        return json.loads(text)
    except Exception as exc:
        logger.debug("remote mcp catalog %s: %s", url, exc)
        return None
