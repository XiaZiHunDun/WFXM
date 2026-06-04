"""SessionEnd hook reasons: clear / finalize / shutdown / end."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.session.lifecycle import trigger_session_end


@pytest.mark.parametrize("reason,marker_name", [
    ("clear", "clear.marker"),
    ("finalize", "finalize.marker"),
    ("shutdown", "shutdown.marker"),
    ("end", "end.marker"),
])
def test_session_end_hook_reason_matcher(tmp_path, monkeypatch, reason, marker_name):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    marker = tmp_path / marker_name
    hook = tmp_path / f"{reason}.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  SessionEnd:
    - matcher: {reason}
      command: sh {hook}
""",
        encoding="utf-8",
    )

    orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    loop = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    loop.messages = []
    trigger_session_end(orch, loop, session_id="sess-x", reason=reason)
    assert marker.is_file()
