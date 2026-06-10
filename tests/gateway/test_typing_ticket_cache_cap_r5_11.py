"""R5-11: TypingTicketCache bounded with TTL sweep."""

from __future__ import annotations

import time

import pytest

from butler.gateway.platforms.wechat_ilink_utils import TypingTicketCache


@pytest.mark.unit
def test_cap_evicts_oldest_when_over_max():
    cache = TypingTicketCache(ttl_seconds=3600.0, max_entries=4)
    for i in range(6):
        cache.set(f"user-{i}", f"ticket-{i}")

    assert cache.get("user-0") is None
    assert cache.get("user-1") is None
    assert cache.get("user-5") == "ticket-5"


@pytest.mark.unit
def test_sweep_expired_before_lru_evict(monkeypatch):
    cache = TypingTicketCache(ttl_seconds=10.0, max_entries=3)
    cache.set("stale", "old")
    monkeypatch.setattr(time, "time", lambda: 100.0)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")

    assert cache.get("stale") is None
    assert cache.get("a") == "1"
