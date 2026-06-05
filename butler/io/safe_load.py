"""Unified safe-load helper for state files (Audit R2-19).

Replaces the 12+ copies of the same anti-pattern found across the
codebase — corrupt YAML/JSON state files silently dropping to a
default value, leaving the operator with no signal that a state file
was bad and the user data was lost.

The unified contract:

* **Missing file** → returns ``default`` (no log, no record).
* **Corrupt file** (parse error) → renames to ``.corrupt-<ns_ts>``
  for forensic retention, logs WARNING with ``exc_info``, records
  the event to the module-level diagnostics buffer, returns
  ``default``.
* **OSError reading** (permission, etc.) → logs WARNING, records,
  returns ``default`` (no rename — we cannot prove the file is
  worth preserving without reading it).
* **Success** → returns parsed data, or ``default`` if the parsed
  result is ``None``.

The diagnostics buffer (``recent_state_file_corruption()``) is
exposed so ``/诊断`` can prompt the user to investigate.

Usage::

    from butler.io.safe_load import safe_load_json, safe_load_yaml

    data = safe_load_json(
        path,
        default={"always": [], "once": [], "pending": None},
        kind="permissions_approvals",
    )

    data = safe_load_yaml(path, default={}, kind="mcp_servers")
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)

_MAX_STATE_CORRUPTION_ENTRIES = 50
_state_file_corruptions: list[dict[str, Any]] = []


def recent_state_file_corruption() -> list[dict[str, Any]]:
    """Return recent state-file corruption events for ``/诊断``."""
    return list(_state_file_corruptions)


def reset_state_file_corruption() -> None:
    """Clear the state-file corruption buffer (test-only)."""
    _state_file_corruptions.clear()


def record_state_file_corruption(
    kind: str, path: Path, error: str, backup: str | None,
) -> None:
    """Public wrapper around the FIFO corruption recorder.

    Callers that need to distinguish "parsed-as-None" (e.g. an empty
    YAML file) from "corrupt / unparseable" (e.g. unbalanced braces)
    use this together with ``quarantine_corrupt_file`` instead of
    the all-in-one ``safe_load_yaml`` helper.  Most callers should
    still prefer ``safe_load_yaml`` / ``safe_load_json`` directly.
    """
    _record_state_file_corruption(kind, path, error, backup)


def quarantine_corrupt_file(path: Path) -> str | None:
    """Public wrapper around ``_quarantine_corrupt_file``.

    Returns the backup path, or ``None`` if the rename failed (or the
    path was a symlink — see module docstring).  Symlinks are left in
    place so downstream atomic-write guards can still reject writes.
    """
    return _quarantine_corrupt_file(path)


def _record_state_file_corruption(
    kind: str, path: Path, error: str, backup: str | None,
) -> None:
    """Append a state-file corruption event (FIFO-capped at 50)."""
    _state_file_corruptions.append(
        {
            "kind": kind,
            "path": str(path),
            "error": error,
            "backup_path": backup,
            "ts": time.time(),
        }
    )
    if len(_state_file_corruptions) > _MAX_STATE_CORRUPTION_ENTRIES:
        del _state_file_corruptions[
            : len(_state_file_corruptions) - _MAX_STATE_CORRUPTION_ENTRIES
        ]


def _quarantine_corrupt_file(path: Path) -> str | None:
    """Rename ``path`` to ``<path>.corrupt-<ns_ts>`` for forensic retention.

    Returns the backup path string, or ``None`` if the rename failed
    (e.g. cross-device, permission denied, or path is a symlink).
    When the rename fails, the original file is left in place —
    callers must decide how to proceed (in our case: still return
    ``default`` to avoid wedging the caller on bad data).

    Symlink handling: if the path is a symlink, we **do not rename
    it**. ``os.replace`` on a symlink replaces the symlink itself
    (not the target), which can break downstream guards that
    expect the symlink to remain (e.g. ``atomic_write_text``'s
    symlink-rejection check). For symlinks, we log the corruption
    but leave the symlink in place.
    """
    if path.is_symlink():
        logger.warning(
            "Corrupt state file %s is a symlink; leaving it in place so "
            "downstream symlink guards can still reject writes.",
            path,
        )
        return None
    backup_name = f"{path.name}.corrupt-{time.time_ns()}"
    backup_path = path.with_name(backup_name)
    try:
        os.replace(path, backup_path)
    except OSError as rename_exc:
        logger.warning(
            "Could not rename corrupt state file %s -> %s: %s",
            path, backup_path, rename_exc,
            exc_info=rename_exc,
        )
        return None
    return str(backup_path)


def safe_load_json(
    path: Path,
    *,
    default: Any,
    kind: str,
) -> Any:
    """Load a JSON state file with safe corruption handling.

    See module docstring for the contract.
    """
    return _safe_load(path, default=default, kind=kind, loader=json.loads)


def safe_load_yaml(
    path: Path,
    *,
    default: Any,
    kind: str,
) -> Any:
    """Load a YAML state file with safe corruption handling.

    See module docstring for the contract.
    """
    return _safe_load(path, default=default, kind=kind, loader=yaml.safe_load)


def _safe_load(
    path: Path,
    *,
    default: Any,
    kind: str,
    loader: Callable[[str], Any],
) -> Any:
    """Implementation shared by ``safe_load_json`` / ``safe_load_yaml``."""
    path = Path(path)
    if not path.is_file():
        return default
    try:
        text = path.read_text(encoding="utf-8")
        data = loader(text)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        if isinstance(exc, OSError):
            logger.warning(
                "Failed to read state file %s (%s): %s",
                path, kind, exc,
                exc_info=exc,
            )
            _record_state_file_corruption(kind, path, str(exc), None)
        else:
            backup = _quarantine_corrupt_file(path)
            logger.warning(
                "Corrupt state file %s (%s), renamed to %s: %s",
                path, kind, backup or "<rename-failed>", exc,
                exc_info=exc,
            )
            _record_state_file_corruption(kind, path, str(exc), backup)
        return default
    return data if data is not None else default
