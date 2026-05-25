"""Prompt eval rubric (tests/fixtures/prompt_eval/cases.yaml)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "fixtures" / "prompt_eval" / "cases.yaml"


@pytest.mark.unit
def test_prompt_eval_cases_all_pass():
    from butler.prompt_eval.runner import run_prompt_eval

    ok, results = run_prompt_eval(cases_path=CASES, repo_root=ROOT)
    failures = [r for r in results if not r.ok]
    assert ok, failures
