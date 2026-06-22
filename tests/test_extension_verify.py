"""Extension Verify (L1) unit tests."""

from __future__ import annotations

import pytest

from butler.mcp.extension_manifest import get_manifest
from butler.mcp.extension_verify import verify_manifest


@pytest.mark.unit
def test_verify_manifest_secrets_only_no_golden(monkeypatch):
    manifest = get_manifest("github-readonly")
    assert manifest is not None
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    report = verify_manifest(manifest, run_golden=False)
    assert report.errors or report.warnings
