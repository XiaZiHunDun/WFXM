"""Tests for Claude Code–style hook stdin JSON."""

import json

from butler.hooks.runner import (
    _hook_payload,
    run_permission_denied_hooks,
    run_pre_tool_hooks,
    run_session_end_hooks,
    run_stop_hooks,
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


def test_pre_tool_hook_fail_closed_blocks_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_HOOK_FAIL_CLOSED", "1")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    hook = tmp_path / "warn.sh"
    hook.write_text('#!/bin/sh\necho soft-fail 1>&2\nexit 1\n', encoding="utf-8")
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
    assert msg and "soft-fail" in msg


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
    from butler.plan.mode import set_plan_mode

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


def test_session_end_hook_runs_for_clear_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    marker = tmp_path / "session_end.marker"
    hook = tmp_path / "end.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  SessionEnd:
    - matcher: clear
      command: sh {hook}
""",
        encoding="utf-8",
    )

    run_session_end_hooks(reason="clear", session_key="s1")
    assert marker.is_file()


def test_stop_hook_matches_status(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    marker = tmp_path / "stop.marker"
    hook = tmp_path / "stop.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  Stop:
    - matcher: completed
      command: sh {hook}
""",
        encoding="utf-8",
    )

    result = run_stop_hooks(
        status="completed", last_assistant_message="done", session_key="s1"
    )
    assert marker.is_file()
    assert not result.additional_context
    marker.unlink()
    run_stop_hooks(status="error", last_assistant_message="fail", session_key="s1")
    assert not marker.exists()


def test_stop_hook_injects_additional_context(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    payload = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": ["metrics-ok"],
            }
        }
    )
    hook = tmp_path / "stop_ctx.sh"
    hook.write_text(f"#!/bin/sh\necho '{payload}'\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  Stop:
    - matcher: "*"
      command: sh {hook}
""",
        encoding="utf-8",
    )

    result = run_stop_hooks(status="completed", session_key="s1")
    assert result.additional_context == ["metrics-ok"]


def test_subagent_start_injects_context(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    payload = json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": ["audit-line"],
            }
        }
    )
    hook = tmp_path / "sub.sh"
    hook.write_text(f"#!/bin/sh\necho '{payload}'\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  SubagentStart:
    - matcher: dev
      command: sh {hook}
""",
        encoding="utf-8",
    )

    from butler.hooks.runner import run_subagent_start_hooks

    ctx = run_subagent_start_hooks(
        agent_type="dev",
        agent_id="task-1",
        task_preview="fix tests",
        session_key="s1",
    )
    assert ctx == ["audit-line"]


def test_health_report_lists_hook_telemetry(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    from butler.hooks.telemetry import record_hook_run
    from butler.ops.health_report import HealthReportInput, build_health_report
    from unittest.mock import MagicMock, patch

    record_hook_run(
        session_key="diag-s",
        event="Stop",
        exit_code=0,
        preview="ok",
    )
    orch = MagicMock()
    orch._settings = MagicMock()
    orch.project_manager.get_current.return_value = None
    with (
        patch(
            "butler.memory.diagnostics.format_memory_diagnostic_lines",
            return_value=[],
        ),
        patch(
            "butler.runtime.diagnostics.format_runtime_diagnostic_lines",
            return_value=[],
        ),
        patch(
            "butler.model_resolve.format_model_diagnostic_lines",
            return_value=[],
        ),
        patch(
            "butler.ops.snapshot.format_ops_diagnostic_lines",
            return_value=[],
        ),
    ):
        text = build_health_report(
            HealthReportInput(
                session_key="diag-s",
                health=None,
                tool_summary={"total": 0, "failed": 0, "codes": []},
                mem_stats={},
                orchestrator=orch,
            )
        )
    assert "Shell hooks 最近" in text
    assert "Stop exit=0" in text


def test_agent_loop_emits_stop_hook(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    marker = tmp_path / "loop_stop.marker"
    hook = tmp_path / "loop_stop.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  Stop:
    - matcher: "*"
      command: sh {hook}
""",
        encoding="utf-8",
    )

    from unittest.mock import MagicMock

    from butler.core.agent_loop import AgentLoop
    from butler.core.loop_types import LoopConfig
    from butler.transport.types import NormalizedResponse

    client = MagicMock()
    client.provider_name = "test"
    client.model = "test"
    resp = NormalizedResponse(content="hi", tool_calls=[])
    client.complete.return_value = resp
    client.stream.return_value = resp
    loop = AgentLoop(client, config=LoopConfig(max_iterations=1, stream=False))
    with monkeypatch.context() as m:
        m.setattr("butler.execution_context.get_current_session_key", lambda: "test-stop")
        loop.run("hello")
    assert marker.is_file()
