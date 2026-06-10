"""R4-7: wechat adapter registry concurrency (satisfied by R1-12 AdapterRegistry)."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from butler.gateway.platforms.wechat_ilink_registry import AdapterRegistry


def _fake_adapter(token: str) -> MagicMock:
    a = MagicMock(spec=["_token"])
    a._token = token
    return a


@pytest.mark.unit
def test_r4_7_registry_concurrent_register_get():
    """Regression for audit R4-7 — cross-thread register/get must not tear."""
    reg = AdapterRegistry()
    errors: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        try:
            barrier.wait(timeout=5)
            for j in range(100):
                tok = f"tok-{i}-{j}"
                adapter = _fake_adapter(tok)
                reg.register(tok, adapter)
                reg.get(tok)
                reg.unregister(tok)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()
    assert not errors, f"adapter registry race: {errors!r}"
