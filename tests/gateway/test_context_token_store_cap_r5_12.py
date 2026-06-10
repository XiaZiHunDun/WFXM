"""R5-12: ContextTokenStore LRU cap bounds memory and persist size."""

from __future__ import annotations

import json

import pytest

from butler.gateway.platforms.wechat_ilink_utils import ContextTokenStore


@pytest.mark.unit
def test_lru_evicts_oldest_entries(tmp_path):
    store = ContextTokenStore(str(tmp_path), max_entries=4)
    for i in range(6):
        store.set("acct", f"user-{i}", f"tok-{i}")

    assert store.get("acct", "user-0") is None
    assert store.get("acct", "user-1") is None
    assert store.get("acct", "user-5") == "tok-5"
    assert store.get("acct", "user-2") == "tok-2"


@pytest.mark.unit
def test_persist_writes_bounded_account_payload(tmp_path):
    store = ContextTokenStore(str(tmp_path), max_entries=3)
    for i in range(5):
        store.set("acct", f"peer-{i}", f"tok-{i}")

    path = tmp_path / "wechat" / "accounts" / "acct.context-tokens.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload) <= 3
    assert "peer-0" not in payload
    assert "peer-4" in payload


@pytest.mark.unit
def test_get_refreshes_lru_order(tmp_path):
    store = ContextTokenStore(str(tmp_path), max_entries=3)
    store.set("acct", "a", "1")
    store.set("acct", "b", "2")
    store.set("acct", "c", "3")
    assert store.get("acct", "a") == "1"
    store.set("acct", "d", "4")

    assert store.get("acct", "b") is None
    assert store.get("acct", "a") == "1"
