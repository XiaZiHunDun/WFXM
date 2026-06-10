"""R5-7: hook telemetry session bucket cap."""

from __future__ import annotations

import pytest

from butler.hooks import telemetry


@pytest.fixture(autouse=True)
def _reset():
    telemetry.reset_hook_telemetry()
    yield
    telemetry.reset_hook_telemetry()


@pytest.mark.unit
def test_session_bucket_cap(monkeypatch):
    monkeypatch.setattr(telemetry, "_MAX_SESSION_BUCKETS", 4)
    for i in range(6):
        telemetry.record_hook_run(session_key=f"sk-{i}", event="PreToolUse", exit_code=0)
    with telemetry._LOCK:
        assert len(telemetry._RECORDS) <= 4
