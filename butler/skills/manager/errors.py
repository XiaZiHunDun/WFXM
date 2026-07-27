from __future__ import annotations

import logging
import threading
from pathlib import Path

from .constants import (
    _SKILL_LOAD_ERROR_BUFFER_MAX,
    SKILL_LOAD_ERR_ENCODING,
    SKILL_LOAD_ERR_IO,
    SKILL_LOAD_ERR_NO_FRONTMATTER,
    SKILL_LOAD_ERR_PATH_TRAVERSAL,
    SKILL_LOAD_ERR_UNTERMINATED,
)

__all__ = [
    "SKILL_LOAD_ERR_ENCODING",
    "SKILL_LOAD_ERR_IO",
    "SKILL_LOAD_ERR_NO_FRONTMATTER",
    "SKILL_LOAD_ERR_PATH_TRAVERSAL",
    "SKILL_LOAD_ERR_UNTERMINATED",
    "SkillLoadError",
    "recent_skill_load_errors",
]

logger = logging.getLogger(__name__)

_skill_load_error_buffer_lock = threading.RLock()
_recent_skill_load_errors: list["SkillLoadError"] = []


class SkillLoadError(Exception):
    code: str
    path: Path
    message: str

    def __init__(self, code: str, path: Path, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.path = path
        self.message = str(message)


def _record_skill_load_error(code: str, path: Path, message: str) -> SkillLoadError:
    err = SkillLoadError(code=code, path=path, message=message)
    with _skill_load_error_buffer_lock:
        _recent_skill_load_errors.append(err)
        if len(_recent_skill_load_errors) > _SKILL_LOAD_ERROR_BUFFER_MAX:
            del _recent_skill_load_errors[
                : len(_recent_skill_load_errors) - _SKILL_LOAD_ERROR_BUFFER_MAX
            ]
    return err


def recent_skill_load_errors(limit: int = 20) -> list[SkillLoadError]:
    if limit <= 0:
        return []
    with _skill_load_error_buffer_lock:
        if limit >= len(_recent_skill_load_errors):
            return list(_recent_skill_load_errors)
        return list(_recent_skill_load_errors[-limit:])


def _clear_recent_skill_load_errors() -> None:
    with _skill_load_error_buffer_lock:
        _recent_skill_load_errors.clear()