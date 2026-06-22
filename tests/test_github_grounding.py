"""GitHub MCP repo-list grounding and direct replies."""

from __future__ import annotations

import json

import pytest

from butler.mcp.bridge import format_call_result
from butler.mcp.github_grounding import (
    format_github_repo_list_reply,
    is_github_repo_list_intent,
    parse_github_repo_list_tool_content,
    try_github_repo_list_direct_reply,
)
from butler.mcp.result_slim import render_github_repo_list_summary


@pytest.mark.unit
def test_github_repo_list_intent():
    assert is_github_repo_list_intent("列出我的github仓库")
    assert is_github_repo_list_intent("list my github repos")
    assert not is_github_repo_list_intent("今天天气怎么样")


@pytest.mark.unit
def test_format_call_result_github_repo_envelope():
    raw = json.dumps(
        [
            {"full_name": "XiaZiHunDun/WFXM", "private": False, "language": "Python"},
            {"full_name": "XiaZiHunDun/LingWen", "private": False, "language": "Python"},
        ]
    )
    out = format_call_result(
        raw,
        tool_name="mcp_github_lst_repos_authenticated_usr",
        server_id="github",
    )
    payload = json.loads(out)
    assert payload["repo_count"] == 2
    assert "WFXM" in payload["summary"]
    assert "LingWen" in payload["summary"]
    assert len(payload["repos"]) == 2


@pytest.mark.unit
def test_direct_reply_short_circuits_hallucination():
    envelope = format_call_result(
        json.dumps([{"full_name": "XiaZiHunDun/WFXM", "private": False}]),
        tool_name="mcp_github_lst_repos_authenticated_usr",
        server_id="github",
    )
    messages = [
        {"role": "user", "content": "列出我的github仓库"},
        {"role": "tool", "content": envelope},
    ]
    reply = try_github_repo_list_direct_reply(messages, user_text="列出我的github仓库")
    assert reply is not None
    assert "WFXM" in reply
    assert "japanese-learning" not in reply


@pytest.mark.unit
def test_github_issue_alias_and_gateway_shortcut(monkeypatch):
    from butler.mcp.github_grounding import try_handle_github_issues_intent
    from butler.mcp.github_tool_aliases import resolve_github_mcp_tool_name

    assert resolve_github_mcp_tool_name("mcp_github_get_issues") == "mcp_github_lst_repo_issues"

    def _fake_dispatch(name, args):
        import json
        return json.dumps({
            "ok": True,
            "code": "MCP_OK",
            "issue_count": 0,
            "owner": args.get("owner", ""),
            "repo": args.get("repo", ""),
            "state": args.get("state", "open"),
            "summary": "（无匹配 issues）",
            "issues": [],
        }, ensure_ascii=False)

    monkeypatch.setattr("butler.mcp.registry_hook.dispatch_mcp_tool", _fake_dispatch)
    reply = try_handle_github_issues_intent("列出WFXM的issues")
    assert reply is not None
    assert "WFXM" in reply
    assert "0 条" in reply or "没有" in reply


@pytest.mark.unit
def test_render_github_repo_list_summary():
    text = render_github_repo_list_summary(
        [
            {
                "full_name": "XiaZiHunDun/TradeSnake",
                "private": True,
                "language": "Python",
                "updated_at": "2026-04-20T04:44:37Z",
            }
        ]
    )
    assert "TradeSnake" in text
    assert "私有" in text
