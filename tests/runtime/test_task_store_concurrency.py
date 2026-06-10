"""R4-2: task_store update_task serializes per task_id."""

from __future__ import annotations

import threading

import pytest

from butler.runtime import task_store


@pytest.mark.unit
def test_concurrent_update_task_preserves_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()

    rec = task_store.create_task(session_key="sess", task_preview="base")
    task_id = rec["task_id"]
    errors: list[BaseException] = []
    errors_lock = threading.Lock()
    barrier = threading.Barrier(6)

    def bump(field: str, value: str) -> None:
        try:
            barrier.wait(timeout=5)
            for _ in range(20):
                task_store.update_task(task_id, **{field: value})
        except BaseException as exc:  # noqa: BLE001
            with errors_lock:
                errors.append(exc)

    fields = [("role", "r1"), ("project", "p1"), ("report_headline", "h1")]
    threads = [
        threading.Thread(target=bump, args=(f, v))
        for f, v in fields
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
        assert not t.is_alive()

    assert not errors, f"concurrent update_task failed: {errors!r}"
    final = task_store.get_task(task_id)
    assert final is not None
    assert final["task_id"] == task_id
    assert final["status"] == "running"
