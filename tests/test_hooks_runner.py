"""Tests for Claude Code–style hook stdin JSON."""

from butler.hooks.runner import _hook_payload, run_pre_tool_hooks


def test_hook_payload_shape():
    pre = _hook_payload("PreToolUse", "read_file", {"path": "a.py"})
    assert pre["hook_event_name"] == "PreToolUse"
    assert pre["tool_name"] == "read_file"
    assert pre["tool_input"]["path"] == "a.py"


def test_pre_tool_hook_blocks_on_exit_2(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    hook = tmp_path / "block.sh"
    hook.write_text('#!/bin/sh\necho blocked 1>&2\nexit 2\n', encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  PreToolUse:
    - matcher: read_file
      command: sh {hook}
""",
        encoding="utf-8",
    )

    msg = run_pre_tool_hooks("read_file", {"path": "x"})
    assert msg and "blocked" in msg
