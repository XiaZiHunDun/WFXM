"""PreCompact hook ACL wiring."""

from __future__ import annotations

from unittest.mock import patch

from butler.core.compaction_task import run_compaction_turn


def test_pre_compact_contexts_adapted_to_diagnostics():
    diag: dict = {}
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(12)]

    def _compress(messages, **kwargs):
        return messages[:4]

    with patch("butler.hooks.runner.run_pre_compact_hooks") as pre_mock:
        from butler.hooks.runner import PreCompactHookResult

        pre_mock.return_value = PreCompactHookResult(
            contexts=['{"summary": "pre hint", "tags": ["t"]}'],
        )
        with patch("butler.hooks.runner.run_post_compact_hooks", return_value=[]):
            did, _ = run_compaction_turn(
                msgs,
                compress=_compress,
                diagnostics=diag,
                iteration=1,
                session_key="sk-pre",
            )
    assert did
    assert "pre hint" in str(diag.get("compaction_pre_hook_context") or "")
    assert diag.get("hook_context_view_version") == "v1"


def test_pre_compact_block_still_short_circuits():
    diag: dict = {}
    msgs = [{"role": "user", "content": "x"}] * 10

    with patch("butler.hooks.runner.run_pre_compact_hooks") as pre_mock:
        from butler.hooks.runner import PreCompactHookResult

        pre_mock.return_value = PreCompactHookResult(blocked="no compact")
        did, out = run_compaction_turn(
            msgs,
            compress=lambda m, **k: m,
            diagnostics=diag,
            iteration=1,
        )
    assert not did
    assert diag.get("compaction_turn_blocked") == "no compact"
    assert len(out) == len(msgs)
