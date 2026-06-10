"""R4-1: tool_result_cache LRU under concurrent get/set."""

from __future__ import annotations

import threading

import pytest

from butler.core import tool_result_cache as cache


@pytest.fixture(autouse=True)
def _clear_cache():
    with cache._STORE_LOCK:
        cache._STORE.clear()
    yield
    with cache._STORE_LOCK:
        cache._STORE.clear()


@pytest.mark.unit
def test_concurrent_set_get_no_exceptions():
    errors: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        try:
            barrier.wait(timeout=5)
            for j in range(50):
                args = {"path": f"/tmp/file-{i}-{j}"}
                cache.set_cached_result("read_file", args, f"body-{i}-{j}", session_key="s1")
                cache.get_cached_result("read_file", args, session_key="s1")
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()

    assert not errors, f"concurrent cache ops failed: {errors!r}"


@pytest.mark.unit
def test_cache_respects_max_per_scope():
    for i in range(250):
        cache.set_cached_result(
            "read_file",
            {"i": i},
            f"r{i}",
            session_key="cap",
        )
    with cache._STORE_LOCK:
        bucket = cache._STORE.get("cap")
        assert bucket is not None
        assert len(bucket) <= cache._MAX_PER_SCOPE
