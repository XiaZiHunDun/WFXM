"""R5-17: SemanticMemoryIndex closes on atexit and explicit shutdown."""

from __future__ import annotations

import sqlite3

import pytest

from butler.memory import semantic_index as si


@pytest.fixture(autouse=True)
def _reset_tracking():
    saved = si._atexit_registered
    si._atexit_registered = False
    si._ACTIVE_INDICES.clear()
    yield
    si._atexit_registered = saved
    si._ACTIVE_INDICES.clear()


@pytest.mark.unit
def test_first_index_registers_atexit(tmp_path):
    assert not si._atexit_registered
    idx = si.SemanticMemoryIndex(tmp_path / "vectors.db")
    assert si._atexit_registered
    assert idx in si._ACTIVE_INDICES
    idx.close()


@pytest.mark.unit
def test_close_all_closes_sqlite_connection(tmp_path):
    idx = si.SemanticMemoryIndex(tmp_path / "vectors.db")
    conn = idx._conn
    assert conn is not None

    si.close_all_semantic_indices()

    assert idx._conn is None
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


@pytest.mark.unit
def test_close_is_idempotent(tmp_path):
    idx = si.SemanticMemoryIndex(tmp_path / "vectors.db")
    idx.close()
    idx.close()
