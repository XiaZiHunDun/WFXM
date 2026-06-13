"""Tests for SWE curriculum playbooks and replay blocks."""

from __future__ import annotations

from butler.dev_engine.swe_curriculum import (
    build_swe_playbook_block,
    format_swe_replay_block,
    get_swe_playbook,
)
from butler.ops.swebench_live_eval import build_swe_delegate_context
from butler.dev_engine.swebench_lite import get_all_instances


def test_swe_012_replay_block_targets_test_file():
    block = format_swe_replay_block("SWE-012")
    assert "test_sorter.py" in block
    assert "is None" in block
    assert "== []" in block
    assert "do NOT change sorter.py" in block


def test_build_swe_delegate_context_includes_swe_012_replay():
    inst = next(i for i in get_all_instances() if i.instance_id == "SWE-012")
    ctx = build_swe_delegate_context(inst)
    assert "SWE ORACLE REPLAY" in ctx
    assert "test_sorter.py" in ctx


def test_swe_014_playbook_exists():
    pb = get_swe_playbook("SWE-014")
    assert pb is not None
    assert "unsubscribe" in pb.pattern_summary.lower()


def test_swe_014_replay_block_includes_patch_hint():
    block = format_swe_replay_block("SWE-014")
    assert "SWE ORACLE REPLAY" in block
    assert "unsubscribe" in block
    assert "self._listeners[event].remove(callback)" in block


def test_build_swe_delegate_context_includes_replay_on_first_attempt():
    inst = next(i for i in get_all_instances() if i.instance_id == "SWE-014")
    ctx = build_swe_delegate_context(inst)
    assert "SWE ORACLE REPLAY" in ctx
    assert "unsubscribe" in ctx.lower()
    assert "write_file entire source" in ctx


def test_swe_015_replay_block_includes_pop_zero_hint():
    block = format_swe_replay_block("SWE-015")
    assert "pop(0)" in block
    assert "pop()" in block
    assert "do NOT reverse sort" in block


def test_build_swe_delegate_context_includes_swe_015_replay():
    inst = next(i for i in get_all_instances() if i.instance_id == "SWE-015")
    ctx = build_swe_delegate_context(inst)
    assert "SWE ORACLE REPLAY" in ctx
    assert "pop(0)" in ctx


def test_unknown_swe_instance_returns_empty_replay():
    assert format_swe_replay_block("SWE-999") == ""
    assert build_swe_playbook_block("SWE-999") == ""


def test_weekly_swe_playbooks_have_skills():
    from pathlib import Path

    from butler.dev_engine.swe_curriculum import SWE_PLAYBOOKS

    skills_root = Path(__file__).resolve().parents[1] / "butler/registry/catalog/skills"
    for pb in SWE_PLAYBOOKS.values():
        assert pb.skill_name
        assert (skills_root / pb.skill_name / "SKILL.md").is_file()
