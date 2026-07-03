"""Document ingest conversion best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path


def convert_document_to_markdown_safe(
    convert_fn: object,
    path: Path,
) -> tuple[str | None, str | None]:
    try:
        text = convert_fn(path)
        return str(text), None
    except Exception as exc:
        return None, str(exc)
