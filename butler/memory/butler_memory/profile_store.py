from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from butler.io.safe_load import safe_load_json

_INJECTION_PATTERNS = re.compile(
    r"(ignore previous|system prompt|you are now|forget everything|\[\[INST\]\])",
    re.IGNORECASE,
)


def _reject_injection(content: str) -> bool:
    return bool(_INJECTION_PATTERNS.search(content))


class ProfileStore:
    """Bounded free-text store (owner profile, preferences, communication style)."""

    def __init__(self, path: Path, char_limit: int = 2000):
        self.path = Path(path)
        self.char_limit = char_limit
        self._lock = threading.Lock()
        self._entries: list[str] = []
        self.load()

    def load(self) -> None:
        with self._lock:
            data = safe_load_json(
                self.path, default={}, kind="memory_experience",
            )
            if not isinstance(data, dict):
                self._entries = []
                return
            entries = data.get("entries", [])
            if not isinstance(entries, list):
                self._entries = []
                return
            self._entries = [str(e).strip() for e in entries if str(e).strip()]

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"entries": self._entries}, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @property
    def total_chars(self) -> int:
        with self._lock:
            return sum(len(e) for e in self._entries)

    def add(self, content: str) -> dict[str, Any]:
        if _reject_injection(content):
            return {"success": False, "error": "Content rejected (suspicious pattern)"}
        content = content.strip()
        if not content:
            return {"success": False, "error": "Empty content"}
        with self._lock:
            if sum(len(e) for e in self._entries) + len(content) > self.char_limit:
                total = sum(len(e) for e in self._entries) + len(content)
                return {
                    "success": False,
                    "error": f"Exceeds character limit ({total}/{self.char_limit}); remove content first",
                }
            self._entries.append(content)
            self._save_unlocked()
        return {"success": True}

    def replace(self, content: str) -> dict[str, Any]:
        if _reject_injection(content):
            return {"success": False, "error": "Content rejected (suspicious pattern)"}
        content = content.strip()
        if len(content) > self.char_limit:
            return {
                "success": False,
                "error": f"Exceeds character limit ({len(content)}/{self.char_limit})",
            }
        with self._lock:
            self._entries = [content] if content else []
            self._save_unlocked()
        return {"success": True}

    def remove(self, keyword: str) -> dict[str, Any]:
        if not keyword.strip():
            return {"success": False, "error": "Empty keyword"}
        key = keyword.strip()
        with self._lock:
            for i, entry in enumerate(self._entries):
                if key in entry:
                    remaining = entry.replace(key, "").strip()
                    if remaining:
                        self._entries[i] = remaining
                    else:
                        self._entries.pop(i)
                    self._save_unlocked()
                    return {"success": True}
        return {"success": False, "error": f"No match for: {key[:50]!r}"}

    def read(self) -> str:
        with self._lock:
            if not self._entries:
                return ""
            return "\n".join(self._entries)

    def _format_for_prompt_unlocked(self) -> str:
        if not self._entries:
            return ""
        return "\n".join(f"- {e}" for e in self._entries)

    def format_for_prompt(self) -> str:
        with self._lock:
            return self._format_for_prompt_unlocked()
