"""Attach local files to WeChat outbound replies (export, audit)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from butler.config import get_butler_home
from butler.env_parse import env_truthy

_PATH_LINE = re.compile(r"^(/[^\s]+)$")

_EXPORT_MAX_BYTES = 5 * 1024 * 1024
_MAX_FILES_PER_MESSAGE = 2


def export_wechat_file_enabled() -> bool:
    return bool(env_truthy("BUTLER_EXPORT_SEND_WECHAT_FILE", default=True))


def export_wechat_max_bytes() -> int:
    raw = os.getenv("BUTLER_EXPORT_SEND_WECHAT_MAX_BYTES", "").strip()
    if not raw:
        return _EXPORT_MAX_BYTES
    try:
        return max(1024, min(20 * 1024 * 1024, int(raw)))
    except ValueError:
        return _EXPORT_MAX_BYTES


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _scan_roots() -> list[Path]:
    roots: list[Path] = [get_butler_home().resolve()]
    for key in ("BUTLER_TOOL_SAFE_ROOT", "BUTLER_PROJECTS_DIR"):
        raw = os.getenv(key, "").strip()
        if raw:
            try:
                roots.append(Path(raw).expanduser().resolve())
            except OSError:
                continue
    return roots


def is_deliverable_export_file(path: str | Path) -> bool:
    """True if path is a regular file under ~/.butler/exports or <workspace>/.butler/exports."""
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return False
    if not resolved.is_file():
        return False
    if resolved.suffix.lower() not in (".md", ".markdown", ".txt"):
        return False
    try:
        if resolved.stat().st_size > export_wechat_max_bytes():
            return False
    except OSError:
        return False

    home_exports = get_butler_home().resolve() / "exports"
    if _is_under(resolved, home_exports):
        return True

    parts = resolved.parts
    if ".butler" not in parts:
        return False
    idx = parts.index(".butler")
    if idx + 1 >= len(parts) or parts[idx + 1] != "exports":
        return False
    for root in _scan_roots():
        if _is_under(resolved, root):
            return True
    return False


def append_wechat_file_delivery_line(text: str, file_path: str | Path) -> str:
    """Append a lone absolute path line so WeChat ``send()`` delivers the file."""
    path = Path(file_path)
    if not export_wechat_file_enabled() or not is_deliverable_export_file(path):
        return text
    line = str(path.resolve())
    body = (text or "").rstrip()
    if line in body:
        return body
    return f"{body}\n\n{line}" if body else line


def extract_deliverable_local_files(content: str) -> tuple[list[str], str]:
    """
    Peel standalone absolute path lines that point to deliverable export files.
    Used by WeChatAdapter.send() before text chunks.
    """
    if not content or not content.strip():
        return [], content

    files: list[str] = []
    kept: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        m = _PATH_LINE.match(stripped)
        if m and len(files) < _MAX_FILES_PER_MESSAGE:
            candidate = m.group(1)
            if is_deliverable_export_file(candidate):
                files.append(str(Path(candidate).resolve()))
                continue
        kept.append(line)

    cleaned = "\n".join(kept).strip()
    if files and not cleaned:
        cleaned = ""
    return files, cleaned


def expand_reply_with_wechat_attachments(reply: str) -> str:
    """Merge deliverable export file bodies into reply text (handler sim rubrics)."""
    files, _ = extract_deliverable_local_files(reply)
    if not files:
        return reply
    parts: list[str] = [reply]
    for fp in files:
        try:
            body = Path(fp).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if body.strip():
            parts.append(body)
    return "\n\n".join(parts)
