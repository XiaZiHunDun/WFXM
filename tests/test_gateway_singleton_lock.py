"""Gateway singleton lock tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
def test_singleton_lock_acquire_and_release(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUTLER_DATA_HOME", str(tmp_path))
    from butler.gateway import singleton_lock as sl

    sl._LOCK_FD = None
    sl.acquire_gateway_singleton_lock()
    assert sl._LOCK_FD is not None
    lock_file = tmp_path / "gateway.singleton.lock"
    assert lock_file.exists()
    # Same process: second acquire is idempotent.
    sl.acquire_gateway_singleton_lock()
    sl.release_gateway_singleton_lock()
    assert sl._LOCK_FD is None
