"""Transcript tail index for large JSONL files."""

from __future__ import annotations

import json
from pathlib import Path

from butler.core.transcript_index import (
    index_enabled_for_size,
    load_tail_rows,
    update_index_after_append,
)


def test_index_tail_read(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUTLER_TRANSCRIPT_INDEX_MIN_BYTES", "100")
    path = tmp_path / "transcript.jsonl"
    rows = []
    offset = 0
    for i in range(30):
        line = json.dumps({"type": "user", "n": i}, ensure_ascii=False) + "\n"
        b = line.encode("utf-8")
        rows.append((offset, len(b)))
        with path.open("ab") as fh:
            fh.write(b)
        update_index_after_append(path, line_byte_offset=offset, line_len=len(b))
        offset += len(b)

    assert index_enabled_for_size(path.stat().st_size)
    tail = load_tail_rows(path, max_lines=5)
    assert len(tail) == 5
    assert tail[-1].get("n") == 29


def test_small_file_full_read(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUTLER_TRANSCRIPT_INDEX_MIN_BYTES", "999999")
    path = tmp_path / "t.jsonl"
    path.write_text('{"type":"a"}\n{"type":"b"}\n', encoding="utf-8")
    tail = load_tail_rows(path, max_lines=10)
    assert len(tail) == 2
