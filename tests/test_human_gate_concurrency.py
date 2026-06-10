"""R4-3: human_gate read/write paths hold _gate_lock."""

from __future__ import annotations

import threading
import time

import pytest

from butler.human_gate import (
    check_workflow_step_approval,
    clear_session_gates,
    is_step_approved,
    mark_step_approved,
)


@pytest.mark.unit
def test_clear_during_approval_check_no_revival(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sk = "gate-conc"
    mark_step_approved(sk, "wf", "step1")
    errors: list[BaseException] = []
    lock = threading.Lock()

    def clearer() -> None:
        try:
            for _ in range(100):
                clear_session_gates(sk)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    def checker() -> None:
        try:
            for _ in range(100):
                check_workflow_step_approval(sk, "wf", "step2")
                is_step_approved(sk, "wf", "step1")
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    t1 = threading.Thread(target=clearer)
    t2 = threading.Thread(target=checker)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive() and not t2.is_alive()
    assert not errors, f"gate concurrency failed: {errors!r}"


@pytest.mark.unit
def test_mark_and_check_under_load(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    sk = "gate-load"
    barrier = threading.Barrier(4)

    def worker(i: int) -> None:
        barrier.wait(timeout=5)
        for j in range(30):
            mark_step_approved(sk, f"wf{i}", f"s{j}")
            assert is_step_approved(sk, f"wf{i}", f"s{j}")
            time.sleep(0)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()
