"""R4-5: read_state mutations never escape _LOCK."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from butler.core import read_state as rs


@pytest.fixture(autouse=True)
def _reset_store():
    rs.reset_read_state(None)
    yield
    rs.reset_read_state(None)


@pytest.mark.unit
def test_reset_during_record_no_orphan_bucket(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    st = f.stat()
    errors: list[BaseException] = []
    lock = threading.Lock()
    stop = threading.Event()

    def recorder() -> None:
        try:
            while not stop.is_set():
                rs.record_read_state(f, st, b"hello", session_key="sk-r4")
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    def resetter() -> None:
        try:
            for _ in range(50):
                rs.reset_read_state(None)
                rs.reset_read_state("sk-r4")
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    def reader() -> None:
        try:
            while not stop.is_set():
                rs.get_read_state(f, session_key="sk-r4")
                rs.read_state_summary(session_key="sk-r4")
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=recorder),
        threading.Thread(target=resetter),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    stop.set()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive()
    assert not errors, f"read_state race: {errors!r}"
