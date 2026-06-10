"""Atomic file writes for yaml/json config (CC Switch subset)."""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write via temp file + fsync + replace to avoid torn or lost writes.

    Sprint 8 REL-3 增强：
      - ``os.fsync`` on tmp before close → 进程崩溃不丢数据
      - 拒绝 symlink 目标（target 已是 symlink）→ 防路径守门绕过
    """
    target = Path(path).expanduser().resolve()
    raw = Path(path).expanduser()
    if raw.is_symlink() or (target.exists() and target.is_symlink()):
        raise OSError(
            f"Refusing to write through symlink: {raw} -> "
            f"{os.readlink(raw) if raw.is_symlink() else os.readlink(target)}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        fd = os.open(
            str(tmp),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        # os.fdopen takes ownership of the descriptor; never close it again here.
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    finally:
        if tmp.is_file() and tmp != target:
            try:
                tmp.unlink()
            except OSError:
                pass


__all__ = ["atomic_write_text"]
