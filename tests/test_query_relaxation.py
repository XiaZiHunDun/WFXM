"""AP-10: query relaxation chain."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.memory.query_relaxation import (
    build_no_result_system_note,
    hybrid_search_with_relaxation,
)


@pytest.mark.unit
def test_relaxation_retries_without_project():
    calls: list[str | None] = []

    def _once(_sem, _fts, _q, *, project=None, limit=8):
        calls.append(project)
        if project:
            return [], "hybrid", 0, True
        return [{"id": 1, "content": "hit", "source": "experience"}], "hybrid", 1, True

    out, mode, _fb, degraded, note = hybrid_search_with_relaxation(
        _once, MagicMock(), MagicMock(), "q", project="demo",
    )
    assert calls == ["demo", None]
    assert out
    assert "relaxed" in mode
    assert note is None


@pytest.mark.unit
def test_relaxation_emits_note_when_still_empty():
    def _once(_sem, _fts, _q, *, project=None, limit=8):
        return [], "fts-error-fallback", 1, True

    _out, _mode, _fb, _deg, note = hybrid_search_with_relaxation(
        _once, None, MagicMock(), "q", project="demo",
    )
    assert note == build_no_result_system_note()
