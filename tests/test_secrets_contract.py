"""G1-13 secrets contract checks."""

from __future__ import annotations

import pytest

from butler.mcp.extension_manifest import get_manifest
from butler.ops.secrets_contract import (
    check_all_secrets_contracts,
    load_platform_contracts,
)


@pytest.mark.unit
def test_platform_contracts_loaded():
    contracts = load_platform_contracts()
    ids = {c.id for c in contracts}
    assert "llm" in ids
    assert "wechat-gateway" in ids


@pytest.mark.unit
def test_extension_manifests_included():
    report = check_all_secrets_contracts(
        gateway_expected=False,
        include_extensions=True,
    )
    assert "github-readonly" in report.extension_ids
    assert "todoist-readonly" in report.extension_ids


@pytest.mark.unit
def test_github_manifest_secret_contract_shape():
    manifest = get_manifest("github-readonly")
    assert manifest is not None
    assert manifest.secrets[0].sync_script.endswith("butler-github-token-sync.sh")
