"""Tests for butler.core.delegate_semaphore."""

from __future__ import annotations

import threading

import pytest

from butler.core.delegate_semaphore import (
    _LOCK,
    _SESSION_SLOTS,
    acquire_delegate_slot,
    max_concurrent_delegates,
    release_delegate_slot,
    running_delegate_count,
    try_acquire_delegate_slot,
)


@pytest.fixture(autouse=True)
def _reset_slots(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BUTLER_DELEGATE_CONCURRENCY_LIMIT", "1")
    monkeypatch.setenv("BUTLER_DELEGATE_MAX_CONCURRENT", "2")
    with _LOCK:
        _SESSION_SLOTS.clear()
    yield
    with _LOCK:
        _SESSION_SLOTS.clear()


def test_acquire_and_release():
    assert try_acquire_delegate_slot("s1")
    assert running_delegate_count("s1") == 1
    release_delegate_slot("s1")
    assert running_delegate_count("s1") == 0


def test_max_concurrent_enforced():
    assert try_acquire_delegate_slot("s1")
    assert try_acquire_delegate_slot("s1")
    assert not try_acquire_delegate_slot("s1")
    assert running_delegate_count("s1") == 2


def test_different_sessions_independent():
    assert try_acquire_delegate_slot("s1")
    assert try_acquire_delegate_slot("s1")
    assert try_acquire_delegate_slot("s2")
    assert try_acquire_delegate_slot("s2")
    assert not try_acquire_delegate_slot("s1")
    assert not try_acquire_delegate_slot("s2")
    release_delegate_slot("s1")
    assert try_acquire_delegate_slot("s1")


def test_context_manager_releases_on_exit():
    with acquire_delegate_slot("s1"):
        assert running_delegate_count("s1") == 1
    assert running_delegate_count("s1") == 0


def test_context_manager_releases_on_exception():
    try:
        with acquire_delegate_slot("s1"):
            raise ValueError("test")
    except ValueError:
        pass
    assert running_delegate_count("s1") == 0


def test_context_manager_raises_when_at_capacity():
    try_acquire_delegate_slot("s1")
    try_acquire_delegate_slot("s1")
    with pytest.raises(RuntimeError, match="上限"):
        with acquire_delegate_slot("s1"):
            pass


def test_disabled_always_allows(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BUTLER_DELEGATE_CONCURRENCY_LIMIT", "0")
    for _ in range(10):
        assert try_acquire_delegate_slot("s1")


def test_release_below_zero_safe():
    release_delegate_slot("nonexistent")
    assert running_delegate_count("nonexistent") == 0


def test_thread_safety():
    acquired = []
    barrier = threading.Barrier(4)

    def _worker():
        barrier.wait()
        result = try_acquire_delegate_slot("ts")
        acquired.append(result)

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert acquired.count(True) == 2
    assert acquired.count(False) == 2
