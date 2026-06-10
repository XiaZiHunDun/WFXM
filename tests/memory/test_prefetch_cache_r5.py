"""R5-1: prefetch cache LRU cap."""

from __future__ import annotations

import pytest

from butler.memory import prefetch_cache as pc


@pytest.fixture(autouse=True)
def _clear_cache():
    with pc._LOCK:
        pc._CACHE.clear()
    yield
    with pc._LOCK:
        pc._CACHE.clear()


@pytest.mark.unit
def test_prefetch_cache_respects_max_entries():
    for i in range(pc._CACHE_MAX + 8):
        pc.set_cached_prefetch("sess", f"query-{i}", f"ctx-{i}")
    with pc._LOCK:
        assert len(pc._CACHE) <= pc._CACHE_MAX
