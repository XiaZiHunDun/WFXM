"""Tests for deterministic static code review."""

from __future__ import annotations

import pytest

from butler.dev_engine.review_static import review_file, run_static_review


@pytest.mark.unit
def test_detects_secret(tmp_path):
    fp = tmp_path / "leak.py"
    fp.write_text("api_key = 'sk-abcdefghijklmnopqrstuvwxyz'\n", encoding="utf-8")
    view = review_file(fp, workspace=tmp_path)
    rules = {f.rule_id for f in view.findings}
    assert "RK-SECURITY" in rules
    assert view.passed is False


@pytest.mark.unit
def test_detects_long_function(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_DEV_REVIEW_MAX_FUNCTION_LINES", "5")
    body = "def big():\n" + "\n".join(f"    v{i} = {i}" for i in range(10)) + "\n    return 0\n"
    fp = tmp_path / "big.py"
    fp.write_text(body, encoding="utf-8")
    view = review_file(fp, workspace=tmp_path)
    assert any(f.rule_id == "RK-SIZE" for f in view.findings)


@pytest.mark.unit
def test_boundary_import_in_core(tmp_path):
    core = tmp_path / "butler" / "core"
    core.mkdir(parents=True)
    fp = core / "bad.py"
    fp.write_text("from butler.gateway.message_handler import X\n", encoding="utf-8")
    view = review_file(fp, workspace=tmp_path)
    assert any(f.rule_id == "RK-BOUNDARY" for f in view.findings)


@pytest.mark.unit
def test_broad_except_warning(tmp_path):
    fp = tmp_path / "swallow.py"
    fp.write_text(
        "def f():\n    try:\n        return 1\n    except Exception:\n        return 0\n",
        encoding="utf-8",
    )
    view = review_file(fp, workspace=tmp_path)
    assert any(f.rule_id == "RK-ERROR" for f in view.findings)


@pytest.mark.unit
def test_run_static_review_empty_workspace(tmp_path):
    view = run_static_review(tmp_path)
    assert view.passed is True
