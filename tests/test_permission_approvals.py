"""P1: session permission approvals and external_directory."""

from __future__ import annotations

from pathlib import Path

from butler.permissions.approvals import (
    ApprovalRequest,
    grant_always,
    grant_once,
    is_approved,
    save_pending,
)
from butler.permissions import (
    check_external_path_override,
    evaluate_external_directory,
    evaluate_permission,
)


def test_external_directory_last_match(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "permissions.yaml").write_text(
        f"""
external_directory:
  - path: "{outside}"
    action: deny
    reason: no outside
  - path: "{outside}"
    action: ask
    reason: outside ask
""",
        encoding="utf-8",
    )
    decision = evaluate_external_directory(str(outside), workspace=ws)
    assert decision is not None
    assert decision.action == "ask"
    assert "outside ask" in decision.reason


def test_grant_once_allows_ask_rule(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "permissions.yaml").write_text(
        """
rules:
  - tool: read_file
    path: "secret.txt"
    action: ask
    reason: need ok
""",
        encoding="utf-8",
    )

    class _Pm:
        def get_current(self, session_key: str = ""):
            class _P:
                workspace = ws

            return _P()

    class _Orch:
        project_manager = _Pm()

    monkeypatch.setattr(
        "butler.execution_context.get_current_orchestrator",
        lambda: _Orch(),
    )
    monkeypatch.setattr(
        "butler.execution_context.get_current_session_key",
        lambda: "wx:test",
    )

    from butler.permissions import check_project_permission_block

    block = check_project_permission_block("read_file", {"path": "secret.txt"})
    assert block is not None and "/批准一次" in block

    req = ApprovalRequest(permission="rule", tool="read_file", pattern="secret.txt")
    save_pending("wx:test", req)
    grant_once("wx:test")
    assert is_approved("wx:test", req)

    block2 = check_project_permission_block("read_file", {"path": "secret.txt"})
    assert block2 is None


def test_grant_always_external_directory(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "permissions.yaml").write_text(
        f"""
external_directory:
  - path: "{outside}*"
    action: ask
    reason: outside ok
""",
        encoding="utf-8",
    )

    class _Pm:
        def get_current(self, session_key: str = ""):
            class _P:
                workspace = ws

            return _P()

    class _Orch:
        project_manager = _Pm()

    monkeypatch.setattr(
        "butler.execution_context.get_current_orchestrator",
        lambda: _Orch(),
    )
    monkeypatch.setattr(
        "butler.execution_context.get_current_session_key",
        lambda: "wx:ext",
    )

    grant_always("wx:ext", permission="external_directory", tool="*", pattern=str(outside))
    override = check_external_path_override(str(outside), for_write=False)
    assert override is not None and override.allowed


def test_make_child_session_transcript_isolated(tmp_path, monkeypatch):
    from butler.core.session_transcript import load_transcript_tail, record_user_message, transcript_path
    from butler.delegate.subagent_permissions import make_child_session_key

    parent = "wx:parent"
    child = make_child_session_key(parent, "task_deadbeef")
    record_user_message(parent, "parent only")
    record_user_message(child, "child only")

    assert transcript_path(parent) != transcript_path(child)
    child_rows = load_transcript_tail(child, max_lines=5)
    assert any(r.get("type") == "user" for r in child_rows)
    parent_rows = load_transcript_tail(parent, max_lines=5)
    previews = [r.get("content_preview", "") for r in parent_rows if r.get("type") == "user"]
    assert "parent only" in previews
    assert "child only" not in previews
