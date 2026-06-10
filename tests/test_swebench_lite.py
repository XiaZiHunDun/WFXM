"""Tests for butler.dev_engine.swebench_lite — SWE-bench Lite adapted benchmark."""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path

from butler.dev_engine.swebench_lite import (
    SWEInstance,
    get_all_instances,
    get_instance,
    get_instances_by_category,
    run_oracle_verification,
)


# ── Instance catalog ──

def test_all_instances_count():
    instances = get_all_instances()
    assert len(instances) == 15


def test_all_instances_unique_ids():
    instances = get_all_instances()
    ids = [i.instance_id for i in instances]
    assert len(ids) == len(set(ids))


def test_all_instances_have_required_fields():
    for inst in get_all_instances():
        assert inst.instance_id, f"Missing instance_id"
        assert inst.category, f"{inst.instance_id}: missing category"
        assert inst.issue_title, f"{inst.instance_id}: missing issue_title"
        assert inst.files, f"{inst.instance_id}: missing files"
        assert inst.oracle_patch, f"{inst.instance_id}: missing oracle_patch"
        assert inst.test_code, f"{inst.instance_id}: missing test_code"


# ── Category distribution ──

def test_category_distribution():
    instances = get_all_instances()
    categories = set(i.category for i in instances)
    assert "bug_fix" in categories
    assert "feature" in categories
    assert "refactor" in categories
    assert "test_fix" in categories


def test_get_instances_by_category():
    bug_fixes = get_instances_by_category("bug_fix")
    assert len(bug_fixes) >= 5


def test_get_instances_by_unknown_category():
    result = get_instances_by_category("nonexistent")
    assert result == []


# ── Instance lookup ──

def test_get_instance_by_id():
    inst = get_instance("SWE-001")
    assert inst is not None
    assert inst.instance_id == "SWE-001"
    assert inst.category == "bug_fix"


def test_get_instance_unknown():
    assert get_instance("SWE-999") is None


# ── Workspace setup ──

def test_setup_workspace():
    inst = get_instance("SWE-001")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        inst.setup_workspace(ws)
        assert (ws / "utils.py").exists()
        content = (ws / "utils.py").read_text()
        assert "range_inclusive" in content


def test_setup_workspace_nested():
    inst = get_instance("SWE-013")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        inst.setup_workspace(ws)
        assert (ws / "api" / "response.py").exists()
        assert (ws / "api" / "__init__.py").exists()


# ── Oracle patch ──

def test_apply_oracle():
    inst = get_instance("SWE-001")
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        inst.setup_workspace(ws)

        before = (ws / "utils.py").read_text()
        assert "range(start, end)" in before

        inst.apply_oracle(ws)

        after = (ws / "utils.py").read_text()
        assert "range(start, end + 1)" in after


# ── Oracle verification (each instance) ──

@pytest.mark.parametrize("instance_id", [
    f"SWE-{i:03d}" for i in range(1, 16)
])
def test_oracle_passes(instance_id):
    """Verify that applying the oracle patch makes the test pass."""
    inst = get_instance(instance_id)
    assert inst is not None, f"Instance {instance_id} not found"

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        inst.setup_workspace(ws)
        inst.apply_oracle(ws)
        assert inst.verify(ws), f"Oracle for {instance_id} failed"


# ── Batch oracle verification ──

def test_run_oracle_verification():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_oracle_verification(Path(tmpdir))
        assert result["total"] == 15
        assert result["passed"] == 15, (
            f"Failed instances: {[r for r in result['results'] if not r['passed']]}"
        )
        assert result["pass_rate"] == 1.0


# ── Difficulty tags ──

def test_difficulty_distribution():
    instances = get_all_instances()
    difficulties = set(i.difficulty for i in instances)
    assert "easy" in difficulties
    assert "medium" in difficulties


def test_all_have_tags():
    for inst in get_all_instances():
        assert len(inst.tags) > 0, f"{inst.instance_id}: missing tags"
