"""Unit tests for novel-factory validate_progress heuristics."""

import importlib.util
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "scripts"
    / "validate_progress.py"
)
_spec = importlib.util.spec_from_file_location("validate_progress", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)


def test_audit_open_issues_batch_status():
    text = "**结论**: 需修改\n| ch001 | 通过 |"
    issues = _mod.audit_open_issues(text)
    assert any("需修改" in i for i in issues)


def test_audit_open_issues_passed_batch():
    text = "| ch104 | 需修改 | 1个P0\n**结论**: 通过\n本批次通过率: 10/10"
    assert _mod.audit_open_issues(text) == []


def test_scan_skipped_when_phase_complete():
    assert _mod.scan_audit_reports(phase="PHASE_COMPLETE") == []
