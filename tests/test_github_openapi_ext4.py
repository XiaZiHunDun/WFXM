"""EXT-4 GitHub OpenAPI readonly spec."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / ".butler/openapi/github-readonly.yml"


@pytest.mark.unit
def test_github_readonly_spec_exists_and_get_only():
    assert SPEC.is_file(), "missing .butler/openapi/github-readonly.yml"
    data = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    paths = data.get("paths") or {}
    assert len(paths) >= 4
    for path, methods in paths.items():
        assert list(methods.keys()) == ["get"], f"{path} must be GET-only"
    ops = {
        methods["get"].get("operationId")
        for methods in paths.values()
        if isinstance(methods, dict) and "get" in methods
    }
    assert ops == {
        "getAuthenticatedUser",
        "listReposForAuthenticatedUser",
        "getRepository",
        "listRepositoryIssues",
    }
