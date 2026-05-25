"""Atomic file writes for yaml/json config (CC Switch subset)."""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write via temp file + replace to avoid torn reads."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        os.replace(tmp, target)
    finally:
        if tmp.is_file() and tmp != target:
            try:
                tmp.unlink()
            except OSError:
                pass


__all__ = ["atomic_write_text"]
