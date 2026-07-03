"""Document conversion fail-closed helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def convert_markitdown_safe(path: Path) -> dict[str, Any]:
    try:
        from markitdown import MarkItDown  # type: ignore[import-untyped]

        md = MarkItDown()
        result = md.convert(str(path))
        text = result.text_content or ""
        return {"ok": True, "text": text}
    except Exception as exc:
        logger.warning("document conversion failed for %s: %s", path, exc)
        return {"error": f"Conversion failed: {exc}", "path": str(path)}
