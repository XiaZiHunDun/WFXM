"""Tests for hashline anchors."""

from __future__ import annotations

from pathlib import Path

from butler.core.hashline import (
    compute_line_hash,
    extract_anchors_from_old_string,
    format_hash_line,
    verify_line_anchors,
)


def test_line_hash_stable():
    h1 = compute_line_hash(1, "hello")
    h2 = compute_line_hash(1, "hello")
    assert h1 == h2
    assert len(h1) >= 1


def test_format_and_verify(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("line one\nline two\n", encoding="utf-8")
    line = format_hash_line(1, "line one")
    anchors = extract_anchors_from_old_string(line)
    assert anchors == [(1, compute_line_hash(1, "line one"))]
    assert verify_line_anchors(path, anchors) is None


def test_mismatch_detected(tmp_path):
    path = tmp_path / "b.txt"
    path.write_text("changed\n", encoding="utf-8")
    bad = format_hash_line(1, "original")
    anchors = extract_anchors_from_old_string(bad)
    err = verify_line_anchors(path, anchors)
    assert err is not None
    assert err.get("code") == "HASHLINE_MISMATCH"
