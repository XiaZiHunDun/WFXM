"""Sprint Codex-C0: canonical approval, execpolicy, compaction phase, auto_review."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from butler.core.compaction_phase import (
    CompactionPhase,
    InitialContextInjection,
    apply_summary_placement,
    resolve_compaction_context,
)
from butler.execpolicy.engine import PolicyDecision, evaluate_command, load_policy_rules
from butler.tools.command_canonicalize import canonicalize_command_for_approval


def test_canonicalize_bash_lc_equivalent():
    a = canonicalize_command_for_approval("/bin/bash -lc 'git status'")
    b = canonicalize_command_for_approval("bash -lc git status")
    assert a == b
    assert "git status" in a


def test_argv_fingerprint_stable_across_bash_path():
    from butler.tools.terminal_approval import argv_fingerprint

    a = argv_fingerprint("/bin/bash -lc 'echo hi'")
    b = argv_fingerprint("bash -lc echo hi")
    assert a == b


def test_execpolicy_git_status_allow():
    with patch.dict(os.environ, {"BUTLER_EXECPOLICY": "1"}, clear=False):
        r = evaluate_command("git status")
    assert r is not None
    assert r.decision == PolicyDecision.ALLOW


def test_execpolicy_builtin_rules_validate():
    rules = load_policy_rules()
    assert any(r.name == "git_readonly" for r in rules)


def test_resolve_compaction_context_mid_turn():
    phase, inj, _ = resolve_compaction_context(iteration=3, explicit_turn=True)
    assert phase == CompactionPhase.MID_TURN
    assert inj == InitialContextInjection.BEFORE_LAST_USER


def test_apply_summary_before_last_user():
    system = [{"role": "system", "content": "sys"}]
    head_tail = [
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "real task"},
    ]
    summary = {"role": "user", "content": "[CONTEXT COMPACTION] sum"}
    out = apply_summary_placement(
        system,
        head_tail,
        summary,
        InitialContextInjection.BEFORE_LAST_USER,
    )
    assert out[-1]["content"] == "real task"
    assert out[-2]["content"] == "[CONTEXT COMPACTION] sum"


def test_auto_review_disabled_by_default():
    from butler.core.auto_review import auto_review_enabled, try_auto_review_terminal

    assert not auto_review_enabled()
    r = try_auto_review_terminal("git status")
    assert r.skipped


def test_format_compaction_detail():
    from butler.core.compaction_status import format_compaction_detail_line

    line = format_compaction_detail_line(
        {"compaction_phase": "mid_turn", "compaction_reason": "auto"},
    )
    assert "mid_turn" in line
