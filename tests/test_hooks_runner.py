"""Tests for Claude Code–style hook stdin JSON."""

import json

from butler.hooks.runner import (
    _hook_payload,
    run_permission_denied_hooks,
    run_pre_tool_hooks,
    run_user_prompt_submit_hooks,
)
from butler.tools.registry import dispatch_tool, reset_tool_audit_events


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


def test_user_prompt_submit_blocks_on_exit_2(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    hook = tmp_path / "block_prompt.sh"
    hook.write_text('#!/bin/sh\necho nope 1>&2\nexit 2\n', encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  UserPromptSubmit:
    - matcher: secret
      command: sh {hook}
""",
        encoding="utf-8",
    )

    result = run_user_prompt_submit_hooks("tell me a secret", session_key="s1")
    assert result.blocked
    assert "nope" in result.block_message


def test_user_prompt_submit_injects_additional_context(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    payload = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": ["ctx-line"],
            }
        }
    )
    hook = tmp_path / "ctx.sh"
    hook.write_text(f"#!/bin/sh\necho '{payload}'\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  UserPromptSubmit:
    - matcher: "*"
      command: sh {hook}
""",
        encoding="utf-8",
    )

    result = run_user_prompt_submit_hooks("hello", session_key="s1")
    assert not result.blocked
    assert result.additional_context == ["ctx-line"]


def test_permission_denied_hook_retry_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    payload = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PermissionDenied",
                "retry": True,
            }
        }
    )
    hook = tmp_path / "perm.sh"
    hook.write_text(f"#!/bin/sh\necho '{payload}'\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  PermissionDenied:
    - matcher: write_file
      command: sh {hook}
""",
        encoding="utf-8",
    )

    hint = run_permission_denied_hooks(
        "write_file",
        {"path": "x"},
        "plan mode blocked",
    )
    assert hint and "retry" in hint.lower()


def test_dispatch_plan_mode_triggers_permission_denied_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings
    from butler.plan_mode import set_plan_mode

    reload_butler_settings()
    payload = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PermissionDenied",
                "retry": True,
            }
        }
    )
    hook = tmp_path / "perm.sh"
    hook.write_text(f"#!/bin/sh\necho '{payload}'\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  PermissionDenied:
    - matcher: delegate_task
      command: sh {hook}
""",
        encoding="utf-8",
    )

    reset_tool_audit_events()
    set_plan_mode("wechat:plan:_", True)
    with monkeypatch.context() as m:
        m.setattr(
            "butler.execution_context.get_current_session_key",
            lambda: "wechat:plan:_",
        )
        raw = dispatch_tool("delegate_task", {"role": "dev", "task": "x"})
    data = json.loads(raw)
    assert data.get("code") == "PLAN_MODE_BLOCKED"
    assert data.get("permission_denied_hint")
