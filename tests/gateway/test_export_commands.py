"""Export slash command wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from butler.gateway.commands.export_handlers import handle_export_session_command


@pytest.mark.unit
def test_export_appends_wechat_file_line(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")

    def _home() -> Path:
        return tmp_path

    monkeypatch.setattr("butler.config.get_butler_home", _home)
    monkeypatch.setattr("butler.gateway.outbound_files.get_butler_home", _home)
    monkeypatch.setattr("butler.core.transcript_export.get_butler_home", _home)

    sk = "wx:owner-export"
    from butler.core.session_transcript import transcript_path

    path = transcript_path(sk)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"type":"user","content_preview":"hi"}\n', encoding="utf-8")

    with patch(
        "butler.gateway.commands.export_handlers.is_gateway_owner",
        return_value=True,
    ):
        reply = handle_export_session_command(
            "",
            platform="wechat",
            external_id="user1",
            session_key=sk,
        )

    assert "已导出" in reply
    deliver = [ln.strip() for ln in reply.splitlines() if ln.strip().endswith(".md")]
    assert deliver
    assert Path(deliver[-1]).is_file()
