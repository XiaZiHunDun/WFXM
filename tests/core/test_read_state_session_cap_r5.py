"""R5-8: read_state session dict cap."""

from __future__ import annotations

import pytest

from butler.core import read_state as rs


@pytest.fixture(autouse=True)
def _reset():
    rs.reset_read_state(None)
    yield
    rs.reset_read_state(None)


@pytest.mark.unit
def test_by_session_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "_MAX_SESSIONS", 4)
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    st = f.stat()
    for i in range(6):
        rs.record_read_state(f, st, b"x", session_key=f"sk-{i}")
    with rs._LOCK:
        assert len(rs._BY_SESSION) <= 4
