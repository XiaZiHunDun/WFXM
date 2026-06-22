"""Extension manifest loader (L0)."""

from __future__ import annotations

import pytest

from butler.mcp.extension_manifest import (
    build_alias_map,
    get_manifest,
    load_all_manifests,
    resolve_tool_alias,
)


@pytest.mark.unit
def test_github_manifest_loaded():
    manifest = get_manifest("github-readonly")
    assert manifest is not None
    assert manifest.ext_id == "ext-4"
    assert manifest.server_id == "github"
    tools = {t.registered for t in manifest.tools}
    assert "mcp_github_lst_repo_issues" in tools


@pytest.mark.unit
def test_manifest_aliases_merge():
    aliases = build_alias_map()
    assert aliases.get("mcp_github_get_issues") == "mcp_github_lst_repo_issues"
    assert (
        resolve_tool_alias("mcp_github_list_repos")
        == "mcp_github_lst_repos_authenticated_usr"
    )


@pytest.mark.unit
def test_load_all_manifests_non_empty():
    manifests = load_all_manifests()
    assert "github-readonly" in manifests
    assert "todoist-readonly" in manifests
    assert "firecrawl" in manifests


@pytest.mark.unit
def test_get_manifest_by_server_id():
    from butler.mcp.extension_manifest import get_manifest_by_server_id

    manifest = get_manifest_by_server_id("todoist")
    assert manifest is not None
    assert manifest.ext_id == "ext-2"
