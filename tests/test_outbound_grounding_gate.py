"""Outbound MCP grounding gate (L3)."""

from __future__ import annotations

import json

import pytest

from butler.mcp.bridge import format_call_result
from butler.mcp.outbound_grounding_gate import try_correct_ungrounded_list_reply


@pytest.mark.unit
def test_outbound_gate_replaces_hallucinated_repo_list():
    envelope = format_call_result(
        json.dumps([{"full_name": "XiaZiHunDun/WFXM", "private": False}]),
        tool_name="mcp_github_lst_repos_authenticated_usr",
        server_id="github",
    )
    messages = [
        {"role": "user", "content": "列出我的github仓库"},
        {"role": "tool", "content": envelope},
    ]
    bad = "主公，你有 10 个仓库：japanese-learning、fake-repo…"
    corrected = try_correct_ungrounded_list_reply(
        "列出我的github仓库",
        bad,
        messages,
    )
    assert corrected is not None
    assert "WFXM" in corrected
    assert "japanese-learning" not in corrected


@pytest.mark.unit
def test_outbound_gate_keeps_grounded_reply():
    envelope = format_call_result(
        json.dumps([{"full_name": "XiaZiHunDun/WFXM", "private": False}]),
        tool_name="mcp_github_lst_repos_authenticated_usr",
        server_id="github",
    )
    messages = [
        {"role": "user", "content": "列出我的github仓库"},
        {"role": "tool", "content": envelope},
    ]
    good = "主公，你的仓库包括 XiaZiHunDun/WFXM"
    assert try_correct_ungrounded_list_reply("列出我的github仓库", good, messages) is None
