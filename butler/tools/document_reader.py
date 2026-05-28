"""Document conversion tool — convert PDF/Word/Excel/PPT to Markdown via markitdown."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_OUTPUT_CHARS = 32_000


def _markitdown_available() -> bool:
    try:
        from markitdown import MarkItDown  # type: ignore[import-untyped]  # noqa: F401
        return True
    except ImportError:
        return False


_SUPPORTED_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt",
    ".html", ".htm", ".csv", ".json", ".xml", ".epub", ".zip",
    ".rtf", ".tsv",
})


def can_convert(path: str) -> bool:
    """Return True if the file extension is supported by markitdown."""
    return Path(path).suffix.lower() in _SUPPORTED_EXTENSIONS


def convert_document(path: str, *, max_chars: int = _MAX_OUTPUT_CHARS) -> dict[str, Any]:
    """Convert a document file to Markdown text.

    Returns dict with keys: ok, path, format, chars, text (or error).
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"File not found: {path}"}

    ext = p.suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        return {"error": f"Unsupported format: {ext}", "supported": sorted(_SUPPORTED_EXTENSIONS)}

    try:
        from markitdown import MarkItDown  # type: ignore[import-untyped]
    except ImportError:
        return {
            "error": "markitdown not installed",
            "hint": "pip install 'butler-system[documents]'",
        }

    try:
        md = MarkItDown()
        result = md.convert(str(p))
        text = result.text_content or ""
    except Exception as exc:
        return {"error": f"Conversion failed: {exc}", "path": str(p)}

    cap = max(500, int(max_chars or _MAX_OUTPUT_CHARS))
    truncated = len(text) > cap
    if truncated:
        text = text[:cap] + "\n…(truncated)"

    return {
        "ok": True,
        "path": str(p),
        "format": ext.lstrip("."),
        "truncated": truncated,
        "chars": len(text),
        "text": text,
    }


def tool_read_document(path: str = "", *, max_chars: int = _MAX_OUTPUT_CHARS, **_: Any) -> str:
    """Tool handler: convert a document to Markdown text."""
    target = (path or "").strip()
    if not target:
        return json.dumps({"error": "path required"})

    if not _markitdown_available():
        return json.dumps({
            "error": "markitdown not installed — document conversion unavailable",
            "hint": "pip install 'butler-system[documents]'",
        })

    result = convert_document(target, max_chars=max_chars)
    return json.dumps(result, ensure_ascii=False)


def register_document_tools(register_fn) -> None:
    """Register read_document tool if markitdown is available."""
    if not _markitdown_available():
        logger.debug("markitdown not installed; read_document tool not registered")
        return

    register_fn(
        name="read_document",
        description=(
            "Convert a document file (PDF, Word, Excel, PowerPoint, HTML, EPUB, etc.) "
            "to Markdown text for reading and analysis. Use for non-plaintext files."
        ),
        schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the document file (PDF, DOCX, XLSX, PPTX, etc.)",
                },
                "max_chars": {
                    "type": "integer",
                    "default": _MAX_OUTPUT_CHARS,
                    "minimum": 500,
                    "maximum": 64000,
                    "description": "Maximum characters to return",
                },
            },
            "required": ["path"],
        },
        handler=tool_read_document,
        toolset="file",
    )


__all__ = [
    "can_convert",
    "convert_document",
    "register_document_tools",
    "tool_read_document",
]
