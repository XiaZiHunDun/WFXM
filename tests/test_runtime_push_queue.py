"""Runtime WeChat push retry queue."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from butler.runtime import notify, push_queue


@pytest.fixture
def butler_home_q(tmp_path, monkeypatch):
    bh = tmp_path / "bh"
    bh.mkdir()
    monkeypatch.setenv("BUTLER_HOME", str(bh))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    return bh


def test_enqueue_on_rate_limit_failure(butler_home_q, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_QUEUE", "1")
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH", "1")
    monkeypatch.setenv("WECHAT_TOKEN", "t")
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "u1")

    async def _rate_limited(**_kwargs):
        return {"error": "rate limited"}

    with patch(
        "butler.gateway.platforms.wechat_ilink.send_wechat_direct",
        side_effect=_rate_limited,
    ):
        ok = notify.push_runtime_message("T", "body")

    assert ok is False
    qpath = butler_home_q / "runtime" / "push_queue.jsonl"
    assert qpath.is_file()
    row = json.loads(qpath.read_text(encoding="utf-8").strip())
    assert row["title"] == "T"


def test_drain_queue_success(butler_home_q, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "0")
    push_queue.enqueue_failed_push("A", "one")
    with patch("butler.runtime.notify.push_runtime_message", return_value=True):
        out = push_queue.drain_push_queue(max_items=2)
    assert out["sent"] == 1
    assert out["remaining"] == 0
