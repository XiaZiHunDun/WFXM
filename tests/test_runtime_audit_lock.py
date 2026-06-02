"""Audit 5.2.5: runtime/audit.try_acquire_lock had a TOCTOU race between
``path.exists()`` and ``atomic_write_text()``; two concurrent acquirers
could both pass the exists-check and both "succeed" — leading to the
same job running twice in parallel.

The fix replaces the check-then-write with ``os.open(O_CREAT|O_EXCL)``
which is an atomic create-or-fail primitive.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from pathlib import Path

import pytest


@pytest.mark.unit
def test_try_acquire_lock_atomic_under_concurrent_calls(monkeypatch, tmp_path):
    """Race the lock acquirer with N threads. With the buggy
    exists-then-write, multiple threads can pass the check and both
    "acquire" the same job. With O_EXCL, exactly one wins."""
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))

    from butler.runtime import audit

    real_exists = Path.exists

    def slow_exists(self, *args, **kwargs):
        # Widen the race window for the buggy code path
        if ".lock" in str(self):
            time.sleep(0.05)
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", slow_exists)

    barrier = threading.Barrier(16)

    def attempt():
        barrier.wait()
        return audit.try_acquire_lock("proj", "race-job")

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(lambda _: attempt(), range(16)))

    true_count = sum(1 for r in results if r)
    assert true_count == 1, (
        f"expected exactly 1 lock acquired under concurrent calls, got {true_count}: "
        f"{results}"
    )


@pytest.mark.unit
def test_try_acquire_lock_creates_file_with_owner_only_perms(monkeypatch, tmp_path):
    """The lock file should be 0o600 so other local users can't squat on it."""
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))

    from butler.runtime import audit

    assert audit.try_acquire_lock("proj", "perm-job") is True
    lock = audit.lock_path("proj", "perm-job")
    assert lock.exists()
    assert oct(lock.stat().st_mode & 0o777) == "0o600", (
        f"lock file should be 0o600, got {oct(lock.stat().st_mode & 0o777)}"
    )
