"""Byte-offset tail index for large session transcript JSONL files."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_INDEX_VERSION = 1
_TAIL_CAP = 500
_INDEX_MIN_BYTES = 256 * 1024


def index_path(transcript_jsonl: Path) -> Path:
    return transcript_jsonl.with_name("transcript.index.json")


def index_min_bytes() -> int:
    raw = os.getenv("BUTLER_TRANSCRIPT_INDEX_MIN_BYTES", "").strip()
    if not raw:
        return _INDEX_MIN_BYTES
    try:
        return max(1, int(raw))
    except ValueError:
        return _INDEX_MIN_BYTES


def index_enabled_for_size(file_size: int) -> bool:
    return file_size >= index_min_bytes()


def invalidate_index(transcript_jsonl: Path) -> None:
    try:
        index_path(transcript_jsonl).unlink(missing_ok=True)
    except OSError:
        pass


def update_index_after_append(transcript_jsonl: Path, *, line_byte_offset: int, line_len: int) -> None:
    """Record start offset of the line just appended."""
    if line_len <= 0:
        return
    try:
        file_size = transcript_jsonl.stat().st_size
    except OSError:
        return
    if not index_enabled_for_size(file_size):
        return

    idx_path = index_path(transcript_jsonl)
    data = _read_index(idx_path)
    if data is None:
        data = {"version": _INDEX_VERSION, "line_count": 0, "file_size": 0, "tail_offsets": []}

    tail: list[int] = list(data.get("tail_offsets") or [])
    tail.append(int(line_byte_offset))
    if len(tail) > _TAIL_CAP:
        tail = tail[-_TAIL_CAP:]

    data["version"] = _INDEX_VERSION
    data["line_count"] = int(data.get("line_count") or 0) + 1
    data["file_size"] = file_size
    data["tail_offsets"] = tail
    _write_index(idx_path, data)


def load_tail_rows(transcript_jsonl: Path, *, max_lines: int) -> list[dict[str, Any]]:
    """Load last max_lines JSON objects; rebuild index lazily when file is large."""
    if not transcript_jsonl.is_file():
        return []
    try:
        file_size = transcript_jsonl.stat().st_size
    except OSError:
        return []

    if not index_enabled_for_size(file_size):
        return _load_tail_full_read(transcript_jsonl, max_lines=max_lines)

    idx_path = index_path(transcript_jsonl)
    data = _read_index(idx_path)
    if data is None or not data.get("tail_offsets"):
        data = _rebuild_index(transcript_jsonl)
        if data:
            _write_index(idx_path, data)

    offsets = list((data or {}).get("tail_offsets") or [])
    if not offsets:
        return _load_tail_full_read(transcript_jsonl, max_lines=max_lines)

    want = min(max_lines, len(offsets))
    selected = offsets[-want:]
    out: list[dict[str, Any]] = []
    try:
        with transcript_jsonl.open("rb") as fh:
            for off in selected:
                fh.seek(off)
                raw = fh.readline()
                if not raw:
                    continue
                try:
                    row = json.loads(raw.decode("utf-8"))
                    if isinstance(row, dict):
                        out.append(row)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
    except OSError as exc:
        logger.debug("Transcript index read failed: %s", exc)
        return _load_tail_full_read(transcript_jsonl, max_lines=max_lines)
    return out


def _load_tail_full_read(path: Path, *, max_lines: int) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in lines[-max_lines:]:
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def _read_index(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_index(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.debug("Transcript index write failed: %s", exc)


def _rebuild_index(transcript_jsonl: Path) -> dict[str, Any] | None:
    offsets: list[int] = []
    try:
        with transcript_jsonl.open("rb") as fh:
            pos = 0
            while True:
                offsets.append(pos)
                line = fh.readline()
                if not line:
                    offsets.pop()  # EOF sentinel
                    break
                pos += len(line)
        file_size = transcript_jsonl.stat().st_size
    except OSError:
        return None
    return {
        "version": _INDEX_VERSION,
        "line_count": len(offsets),
        "file_size": file_size,
        "tail_offsets": offsets[-_TAIL_CAP:],
    }
