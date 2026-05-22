"""Push queue deduplication by content hash."""

import pytest

from butler.runtime import push_queue


@pytest.fixture
def butler_home_q(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    return tmp_path


def test_enqueue_dedupes_same_payload(butler_home_q, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(butler_home_q))
    push_queue.enqueue_failed_push("T", "body one", chat_id="u1")
    push_queue.enqueue_failed_push("T", "body one", chat_id="u1")
    path = butler_home_q / "runtime" / "push_queue.jsonl"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
