"""P2: explicit compaction turn, compact hooks, todo priority, subagent deny."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from butler.core.compaction_task import (
    explicit_compaction_turn_enabled,
    run_compaction_turn,
    should_run_compaction_turn,
)
from butler.core.session_todos import (
    load_session_todos,
    replace_session_todos,
    session_todos_enabled,
)
from butler.delegate.subagent_permissions import filter_tools_for_subagent


@pytest.mark.unit
def test_should_run_compaction_turn_over_threshold():
    msgs = [{"role": "user", "content": "x" * 50000}]
    diag: dict = {}
    assert should_run_compaction_turn(
        msgs,
        max_context_tokens=10_000,
        estimate_tokens=lambda m: 50_000,
        diagnostics=diag,
        iteration=1,
    )


@pytest.mark.unit
def test_compaction_turn_not_twice_same_iteration():
    msgs = [{"role": "user", "content": "x" * 1000}]
    diag = {"compaction_turn_iteration": 2}
    assert not should_run_compaction_turn(
        msgs,
        max_context_tokens=100,
        estimate_tokens=lambda m: 10_000,
        diagnostics=diag,
        iteration=2,
    )


@pytest.mark.unit
def test_agent_compress_context_forwards_diagnostics(mock_llm_client):
    from butler.core.agent_loop import AgentLoop, LoopConfig

    loop = AgentLoop(mock_llm_client, config=LoopConfig(max_context_tokens=128000))
    diag = {"compaction_explicit_turn": True, "compaction_turn_iteration": 2}
    with patch.object(
        loop._context,
        "compress_context",
        return_value=[{"role": "user", "content": "ok"}],
    ) as mock_compress:
        out = loop._compress_context(
            [{"role": "user", "content": "x" * 100}],
            diagnostics=diag,
            initial_injection=None,
        )
    assert out
    mock_compress.assert_called_once()
    assert mock_compress.call_args.kwargs.get("diagnostics") is diag


@pytest.mark.unit
def test_run_compaction_turn_records_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    sk = "test-compact-turn"
    msgs = [{"role": "system", "content": "s"}]
    for _ in range(10):
        msgs.append({"role": "user", "content": "y" * 300})
        msgs.append({"role": "assistant", "content": "z" * 300})

    def _compress(m, **kwargs):
        return m[:4]

    did, out = run_compaction_turn(
        msgs,
        compress=_compress,
        diagnostics={},
        iteration=1,
        session_key=sk,
    )
    assert did
    assert len(out) < len(msgs)
    from butler.core.session_transcript import load_transcript_tail

    rows = load_transcript_tail(sk, max_lines=20)
    assert any(r.get("type") == "compaction_turn" for r in rows)


@pytest.mark.unit
def test_pre_compact_hook_blocks(monkeypatch, tmp_path):
    ws = tmp_path / "proj"
    (ws / ".butler").mkdir(parents=True)
    (ws / ".butler" / "hooks.yaml").write_text(
        """
hooks:
  PreCompact:
    - matcher: "*"
      command: "echo blocked >&2; exit 2"
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
    from butler.hooks.runner import run_pre_compact_hooks

    block = run_pre_compact_hooks(estimated_tokens=1000, message_count=10)
    assert block.blocked is not None


@pytest.mark.unit
def test_todo_priority_sort(tmp_butler_home, monkeypatch):
    if not session_todos_enabled():
        monkeypatch.setenv("BUTLER_SESSION_TODOS", "1")
    sk = "wx:todo-pri"
    replace_session_todos(
        sk,
        [
            {"id": "1", "content": "low task", "priority": "low"},
            {"id": "2", "content": "high task", "priority": "high"},
            {"id": "3", "content": "med task", "priority": "medium"},
        ],
    )
    items = load_session_todos(sk)
    assert items[0]["id"] == "2"
    assert items[-1]["id"] == "1"


@pytest.mark.unit
def test_subagent_denies_session_todos_tools(tmp_path):
    ws = tmp_path / "p"
    ws.mkdir()
    tools = [
        {"function": {"name": "read_file"}},
        {"function": {"name": "session_todos_write"}},
        {"function": {"name": "session_todos_list"}},
    ]
    filtered = filter_tools_for_subagent(tools, workspace=ws, role="dev")
    names = {t["function"]["name"] for t in filtered}
    assert "read_file" in names
    assert "session_todos_write" not in names
    assert "session_todos_list" not in names


@pytest.mark.unit
def test_post_edit_format_disabled_by_default(tmp_path):
    from butler.core.post_edit_format import maybe_format_after_edit, post_edit_format_enabled

    assert not post_edit_format_enabled()
    py = tmp_path / "a.py"
    py.write_text("x=1\n", encoding="utf-8")
    assert maybe_format_after_edit(py) is None
