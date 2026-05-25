"""Gateway /queue slash command."""

from __future__ import annotations

from tests.test_gateway_handler import _reset_singletons


def test_queue_slash_command(tmp_path, monkeypatch, tmp_butler_home):
    from butler.gateway.message_handler import ButlerMessageHandler
    from butler.gateway.queue_settings import clear_session_override, get_queue_mode

    empty_projects = tmp_path / "empty-projects"
    empty_projects.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(empty_projects))
    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    sk = "wechat:queue-u1"

    clear_session_override(sk)
    out = handler._handle_command("/queue collect cap:3", session_key=sk)
    assert "collect" in out
    assert get_queue_mode(sk) == "collect"

    out_reset = handler._handle_command("/queue reset", session_key=sk)
    assert "默认" in out_reset
    clear_session_override(sk)
