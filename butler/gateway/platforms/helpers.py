"""Shared helpers for Butler gateway platform adapters."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from butler.io.atomic_write import atomic_write_text


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Serialize payload to JSON and write atomically (fsync + no symlink).

    Sprint 8 REL-3：原实现裸 write_text + replace，缺 fsync（崩溃丢数据）
    与 O_NOFOLLOW（可写到 symlink 目标绕过路径守门）。改为复用
    ``butler.io.atomic_write_text``。
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    atomic_write_text(path, text)


class MessageDeduplicator:
    def __init__(self, max_size: int = 2000, ttl_seconds: float = 300):
        self._seen: dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds

    def is_duplicate(self, msg_id: str) -> bool:
        if not msg_id:
            return False
        now = time.time()
        if msg_id in self._seen:
            if now - self._seen[msg_id] < self._ttl:
                return True
            del self._seen[msg_id]
        self._seen[msg_id] = now
        if len(self._seen) > self._max_size:
            cutoff = now - self._ttl
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        return False
