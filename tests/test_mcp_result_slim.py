"""MCP verbose result slimming."""

from __future__ import annotations

import json

import pytest

from butler.mcp.bridge import format_call_result
from butler.mcp.result_slim import slim_mcp_raw_result


@pytest.mark.unit
def test_slim_github_repo_list():
    raw = json.dumps(
        [
            {
                "id": 1,
                "full_name": "XiaZiHunDun/WFXM",
                "private": False,
                "visibility": "public",
                "fork": False,
                "updated_at": "2026-06-22T07:20:15Z",
                "language": "Python",
                "description": "x" * 200,
                "owner": {"login": "XiaZiHunDun"},
                "permissions": {"admin": True},
            },
            {
                "id": 2,
                "full_name": "XiaZiHunDun/LingWen",
                "private": False,
                "visibility": "public",
                "fork": False,
                "updated_at": "2026-06-22T06:55:40Z",
                "language": "Python",
                "description": None,
                "owner": {"login": "XiaZiHunDun"},
            },
        ],
        ensure_ascii=False,
    )
    slim = slim_mcp_raw_result(
        raw,
        tool_name="mcp_github_lst_repos_authenticated_usr",
        server_id="github",
    )
    data = json.loads(slim)
    assert len(data) == 2
    assert data[0]["full_name"] == "XiaZiHunDun/WFXM"
    assert "owner" not in data[0]
    assert "permissions" not in data[0]
    assert len(data[0]["description"]) == 120
    assert len(slim) < len(raw)


@pytest.mark.unit
def test_format_call_result_applies_github_slim():
    huge = json.dumps([{"full_name": f"o/r{i}", "private": False} for i in range(12)])
    out = format_call_result(
        huge,
        tool_name="mcp_github_lst_repos_authenticated_usr",
        server_id="github",
    )
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["repo_count"] == 12
    assert len(payload["repos"]) == 12
    assert payload["repos"][0]["full_name"] == "o/r0"


@pytest.mark.unit
def test_slim_ignores_non_github():
    raw = '{"full_name":"a/b"}'
    assert slim_mcp_raw_result(raw, tool_name="mcp_x", server_id="todoist") == raw
