"""Tests for production playbook seeds (Phase C)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary
from butler.dev_engine.prod_playbook_seeds import (
    PROD_PLAYBOOK_SEEDS,
    build_prod_playbook_blocks,
    match_prod_playbook_triggers,
    seed_prod_playbooks,
    verify_prod_playbook_retrieval,
)
from butler.memory.memory_scope import tenant_coding_experiences_path


@pytest.mark.unit
def test_match_prod_playbook_triggers_path_and_verify():
    hits = match_prod_playbook_triggers(
        "fix verify_fail pytest",
        "LingWen1/docs missing file not found",
    )
    ids = {h.experience_id for h in hits}
    assert "PROD_PLAYBOOK_delegate_rescue" in ids
    assert "PROD_PLAYBOOK_path_error" in ids


@pytest.mark.unit
def test_build_prod_playbook_blocks_non_empty():
    blocks = build_prod_playbook_blocks("read_file before patch", "")
    assert blocks
    assert any("PROD_PLAYBOOK_read_state" in b for b in blocks)


@pytest.mark.unit
def test_seed_and_retrieval(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    l4 = tenant_coding_experiences_path(tmp_path)
    l4.parent.mkdir(parents=True, exist_ok=True)
    if not l4.is_file():
        l4.write_text("[]", encoding="utf-8")

    dry = seed_prod_playbooks(butler_home=tmp_path, dry_run=True)
    assert dry["total"] == len(PROD_PLAYBOOK_SEEDS)

    applied = seed_prod_playbooks(butler_home=tmp_path, dry_run=False)
    assert applied["ok"] is True
    rows = json.loads(l4.read_text(encoding="utf-8"))
    ids = {r.get("id") for r in rows}
    for seed in PROD_PLAYBOOK_SEEDS:
        assert seed.experience_id in ids

    xlib2 = ExperienceLibrary.load_from_file(str(l4), theorem_lib=TheoremLibrary())
    found = xlib2.search({"read_file", "before", "patch"}, set(), strict_coverage=False)
    assert any(h.id == "PROD_PLAYBOOK_read_state" for h in found)


@pytest.mark.unit
def test_prod_delegate_bridge_includes_playbook_blocks():
    from butler.dev_engine.prod_delegate_bridge import build_production_delegate_blocks

    blocks = build_production_delegate_blocks(
        "pytest verify failed need patch",
        "path LingWen1/docs wrong",
        category="deep",
    )
    merged = "\n".join(blocks)
    assert "PROD PLAYBOOK" in merged
