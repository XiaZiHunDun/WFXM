"""Builtin tool orthogonality lint."""

from __future__ import annotations

import pytest

from butler.tools.orthogonality_lint import lint_builtin_tool_orthogonality


@pytest.mark.unit
def test_orthogonality_lint_runs():
    issues = lint_builtin_tool_orthogonality(threshold=0.99)
    assert isinstance(issues, list)
