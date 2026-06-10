"""R4-4: provider circuit breaker mutations stay inside _STATE_LOCK."""

from __future__ import annotations

import threading

import pytest

from butler.transport import provider_health as ph


@pytest.fixture(autouse=True)
def _reset_state():
    with ph._STATE_LOCK:
        ph._STATE.clear()
    yield
    with ph._STATE_LOCK:
        ph._STATE.clear()


@pytest.mark.unit
def test_concurrent_failure_and_open_check(monkeypatch):
    monkeypatch.setenv("BUTLER_PROVIDER_CIRCUIT_FAILURES", "3")
    errors: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            for _ in range(30):
                ph.record_provider_failure("prov", "model")
                ph.is_circuit_open("prov", "model")
                ph.record_provider_success("prov", "model")
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()
    assert not errors, f"circuit breaker race: {errors!r}"
