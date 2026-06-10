"""R5-10: observer queue workspace cap."""

from __future__ import annotations

import pytest

from butler.memory import observer_queue as oq


@pytest.fixture(autouse=True)
def _reset():
    oq.clear_observer_queue()
    yield
    oq.clear_observer_queue()


@pytest.mark.unit
def test_workspace_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(oq, "_MAX_WORKSPACES", 3)
    for i in range(5):
        ws = tmp_path / f"ws-{i}"
        ws.mkdir()
        with oq._LOCK:
            oq._queue_for_key(str(ws.resolve()))
    with oq._LOCK:
        assert len(oq._QUEUES) <= 3
