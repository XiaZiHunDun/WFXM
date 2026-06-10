"""Edit operation algebra — atomic write, patch, multi-edit with rollback.

Formal model from v4-dev-engine-theory.md §2.2:
  Edit ::= Write(p, c) | Patch(p, old, new) | Delete(p) | Create(p, c)
  MultiEdit([e1..en]) = all-or-nothing transactional
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from butler.dev_engine.dev_state import EditRecord

logger = logging.getLogger(__name__)


def _snapshot_file(path: Path) -> str | None:
    """Read current file content for undo support. Returns None if not exists."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def apply_write(path: Path, content: str) -> tuple[EditRecord | None, str]:
    """Write full file content. Returns (record, error).

    Implements Definition D3: Write(p, c).
    Uses atomic write (DA1) via temp+rename.
    """
    original = _snapshot_file(path)
    try:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(path, content)
    except OSError as exc:
        return None, f"Write failed: {exc}"

    record = EditRecord(
        operation="write",
        path=str(path),
        original_content=original,
        new_content=content,
    )
    return record, ""


def apply_patch(path: Path, old: str, new: str) -> tuple[EditRecord | None, str]:
    """Replace exact occurrence in file. Returns (record, error).

    Implements Definition D3: Patch(p, old, new).
    Requires exactly one match (uniqueness constraint).
    """
    current = _snapshot_file(path)
    if current is None:
        return None, f"Cannot patch: file not found or unreadable: {path}"

    count = current.count(old)
    if count == 0:
        return None, f"Patch failed: old string not found in {path.name}"
    if count > 1:
        return None, f"Patch failed: old string has {count} matches in {path.name}, must be unique"

    patched = current.replace(old, new, 1)
    try:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(path, patched)
    except OSError as exc:
        return None, f"Patch write failed: {exc}"

    record = EditRecord(
        operation="patch",
        path=str(path),
        original_content=current,
        new_content=patched,
        patch_old=old,
        patch_new=new,
    )
    return record, ""


def apply_create(path: Path, content: str) -> tuple[EditRecord | None, str]:
    """Create a new file. Fails if file already exists.

    Implements Definition D3: Create(p, c).
    """
    if path.exists():
        return None, f"Create failed: file already exists: {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(path, content)
    except OSError as exc:
        return None, f"Create failed: {exc}"

    record = EditRecord(
        operation="create",
        path=str(path),
        new_content=content,
    )
    return record, ""


def apply_delete(path: Path) -> tuple[EditRecord | None, str]:
    """Delete a file. Snapshots content for undo.

    Implements Definition D3: Delete(p).
    """
    original = _snapshot_file(path)
    if original is None and not path.exists():
        return None, f"Delete failed: file not found: {path}"
    try:
        path.unlink()
    except OSError as exc:
        return None, f"Delete failed: {exc}"

    record = EditRecord(
        operation="delete",
        path=str(path),
        original_content=original,
    )
    return record, ""


def undo_edit(record: EditRecord) -> str:
    """Undo a single edit operation (Definition D5).

    Returns error string on failure, empty string on success.
    """
    path = Path(record.path)
    op = record.operation

    if op == "write":
        if record.original_content is None:
            return f"Cannot undo write: no original snapshot for {path}"
        try:
            from butler.io.atomic_write import atomic_write_text

            atomic_write_text(path, record.original_content)
        except OSError as exc:
            return f"Undo write failed: {exc}"

    elif op == "patch":
        if record.original_content is None:
            return f"Cannot undo patch: no original snapshot for {path}"
        try:
            from butler.io.atomic_write import atomic_write_text

            atomic_write_text(path, record.original_content)
        except OSError as exc:
            return f"Undo patch failed: {exc}"

    elif op == "create":
        try:
            path.unlink()
        except OSError as exc:
            return f"Undo create failed: {exc}"

    elif op == "delete":
        if record.original_content is None:
            return f"Cannot undo delete: no original content for {path}"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from butler.io.atomic_write import atomic_write_text

            atomic_write_text(path, record.original_content)
        except OSError as exc:
            return f"Undo delete failed: {exc}"
    else:
        return f"Unknown operation: {op}"

    return ""


def rollback_edits(records: list[EditRecord]) -> list[str]:
    """Rollback a sequence of edits in reverse order (DT5).

    Returns list of errors (empty list = full success).
    """
    errors: list[str] = []
    for record in reversed(records):
        err = undo_edit(record)
        if err:
            errors.append(err)
            logger.warning("Rollback partial failure: %s", err)
    return errors


def multi_edit(
    edits: list[tuple[str, Path, dict]],
) -> tuple[list[EditRecord], str]:
    """Execute multiple edits as a transaction (Definition D4).

    Args:
        edits: List of (op_type, path, kwargs) tuples.
               op_type: "write" | "patch" | "create" | "delete"

    Returns:
        (records, error). On error, all edits are rolled back.
    """
    records: list[EditRecord] = []
    dispatch = {
        "write": lambda p, kw: apply_write(p, kw["content"]),
        "patch": lambda p, kw: apply_patch(p, kw["old"], kw["new"]),
        "create": lambda p, kw: apply_create(p, kw["content"]),
        "delete": lambda p, kw: apply_delete(p),
    }

    for op_type, path, kwargs in edits:
        handler = dispatch.get(op_type)
        if handler is None:
            rollback_edits(records)
            return [], f"Unknown edit operation: {op_type}"

        record, err = handler(path, kwargs)
        if err:
            rollback_edits(records)
            return [], f"MultiEdit failed at {op_type}({path}): {err}"
        if record:
            records.append(record)

    return records, ""
