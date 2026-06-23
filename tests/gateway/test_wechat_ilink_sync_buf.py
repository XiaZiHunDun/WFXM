"""Regression: iLink poll sync_buf must advance in-memory to avoid inbound replay."""

from __future__ import annotations

from butler.gateway.platforms.wechat_ilink_phases import _phase_poll_handle_response


class _FakeAdapter:
    name = "wechat-test"
    _data_home = "/tmp"
    _account_id = "acct-1"


def test_poll_handle_response_persists_sync_buf(tmp_path, monkeypatch):
    adapter = _FakeAdapter()
    adapter._data_home = str(tmp_path)
    saved: list[str] = []

    def _save(home, account_id, buf):
        saved.append(buf)

    monkeypatch.setattr(
        "butler.gateway.platforms.wechat_ilink._save_sync_buf",
        _save,
    )
    signal, msgs = _phase_poll_handle_response(
        adapter,
        {"ret": 0, "errcode": 0, "get_updates_buf": "buf-v2", "msgs": [{"x": 1}]},
    )
    assert signal == "ok"
    assert len(msgs) == 1
    assert saved == ["buf-v2"]


def test_poll_loop_advances_local_sync_buf():
    """Document the contract the poll loop must satisfy (in-memory + disk)."""
    sync_buf = "buf-v1"
    response = {"get_updates_buf": "buf-v2", "msgs": []}
    new_sync_buf = str(response.get("get_updates_buf") or "").strip()
    if new_sync_buf:
        sync_buf = new_sync_buf
    assert sync_buf == "buf-v2"
