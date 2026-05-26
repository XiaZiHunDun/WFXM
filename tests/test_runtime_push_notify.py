"""Runtime WeChat push cooldown."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

from butler.runtime import notify


@pytest.fixture
def butler_home_push(tmp_path, monkeypatch):
    bh = tmp_path / "bh"
    bh.mkdir()
    monkeypatch.setenv("BUTLER_HOME", str(bh))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    return bh


def test_push_cooldown_waits(butler_home_push, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "2")
    notify._write_last_push_monotonic(time.monotonic() - 0.5)

    slept = []
    monkeypatch.setattr(notify.time, "sleep", lambda s: slept.append(s))
    wait = notify._wait_push_cooldown()

    assert wait > 0
    assert slept and slept[0] > 0


def test_push_records_timestamp_on_success(butler_home_push, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH", "1")
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("WECHAT_TOKEN", "t")
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "user1")

    async def _fake_send(**_kwargs):
        return {}

    with patch(
        "butler.gateway.platforms.wechat_ilink.send_wechat_direct",
        side_effect=_fake_send,
    ):
        ok = notify.push_runtime_message("t", "body")

    assert ok is True
    path = butler_home_push / "runtime" / "last_push_at.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "monotonic" in data


def test_push_uses_gateway_allowlist_fallback(butler_home_push, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH", "1")
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("WECHAT_TOKEN", "t")
    monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
    monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
    monkeypatch.setenv("BUTLER_GATEWAY_ALLOWLIST", "legacy1,legacy2")

    seen: dict[str, str] = {}

    async def _fake_send(**kwargs):
        seen["chat_id"] = kwargs["chat_id"]
        return {}

    with patch(
        "butler.gateway.platforms.wechat_ilink.send_wechat_direct",
        side_effect=_fake_send,
    ):
        ok = notify.push_runtime_message("t", "body")

    assert ok is True
    assert seen["chat_id"] == "legacy1"
