"""R4-6: merge_session_todos load-merge-write under _LOCK."""

from __future__ import annotations

import threading

import pytest

from butler.core.session_todos import load_session_todos, merge_session_todos, replace_session_todos


@pytest.mark.unit
def test_concurrent_merge_retains_all_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sk = "cli:conc-merge"
    replace_session_todos(sk, [])
    errors: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(6)

    def add_todo(i: int) -> None:
        try:
            barrier.wait(timeout=5)
            merge_session_todos(
                sk,
                [{"id": f"t{i}", "content": f"task {i}", "status": "pending"}],
            )
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=add_todo, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()

    assert not errors, f"merge race: {errors!r}"
    items = load_session_todos(sk)
    ids = {t["id"] for t in items}
    assert len(ids) == 6, f"expected 6 todos, got {ids}"
