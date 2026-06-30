"""Guard hook result dataclasses against field regressions (ENG-9 / ACL)."""

from __future__ import annotations

from dataclasses import fields

from butler.hooks.runner import PreCompactHookResult, StopHookResult


def test_stop_hook_result_has_block_fields():
    names = {f.name for f in fields(StopHookResult)}
    assert {"additional_context", "blocked", "block_message", "decision"} <= names


def test_pre_compact_hook_result_shape():
    names = {f.name for f in fields(PreCompactHookResult)}
    assert names == {"blocked", "contexts"}
    r = PreCompactHookResult(blocked="stop", contexts=["x"])
    assert r.blocked == "stop"
    assert r.contexts == ["x"]
