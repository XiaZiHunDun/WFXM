"""Deterministic GitHub repo-list replies (EXT-4 grounding)."""

from __future__ import annotations

import json
import re
from typing import Any, cast

from butler.env_parse import env_truthy
from butler.mcp.extension_grounding import matches_manifest_intent

_GITHUB_REPO_LIST_INTENT = re.compile(
    r"(列出|列举|list|显示|查看|查|看看).{0,16}"
    r"(github|gh|GitHub).{0,16}(仓库|repo|repositories)?",
    re.IGNORECASE,
)

_GITHUB_ISSUE_LIST_INTENT = re.compile(
    r"(issues?|问题|工单)",
    re.IGNORECASE,
)


def github_issue_list_direct_enabled() -> bool:
    return bool(env_truthy("BUTLER_GITHUB_ISSUE_LIST_DIRECT", default=True))


def github_repo_list_direct_enabled() -> bool:
    return bool(env_truthy("BUTLER_GITHUB_REPO_LIST_DIRECT", default=True))


def is_github_repo_list_intent(text: str) -> bool:
    if matches_manifest_intent(text, kind="repo_list", server_id="github"):
        return True
    raw = str(text or "").strip()
    if not raw:
        return False
    if _GITHUB_REPO_LIST_INTENT.search(raw):
        return True
    lowered = raw.lower()
    return "github" in lowered and any(k in raw for k in ("列出", "仓库", "repo"))


def parse_github_repo_list_tool_content(content: str) -> dict[str, Any] | None:
    text = str(content or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("code") != "MCP_OK":
        return None
    if int(payload.get("repo_count") or 0) <= 0:
        return None
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        repos = payload.get("repos")
        if isinstance(repos, list) and repos:
            from butler.mcp.result_slim import render_github_repo_list_summary

            summary = render_github_repo_list_summary(repos)
            payload["summary"] = summary
    if not summary:
        return None
    return payload


def find_latest_github_repo_list_envelope(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        envelope = parse_github_repo_list_tool_content(str(msg.get("content") or ""))
        if envelope is not None:
            return envelope
    return None


def format_github_repo_list_reply(envelope: dict[str, Any]) -> str:
    count = int(envelope.get("repo_count") or 0)
    summary = str(envelope.get("summary") or "").strip()
    login = str(envelope.get("login") or "").strip()
    head = "主公，你的 GitHub"
    if login:
        head += f" ({login})"
    head += f" 共有 {count} 个仓库：\n\n"
    return head + summary


def try_github_repo_list_direct_reply(
    messages: list[dict[str, Any]],
    *,
    user_text: str,
) -> str | None:
    if not github_repo_list_direct_enabled():
        return None
    if not is_github_repo_list_intent(user_text):
        return None
    envelope = find_latest_github_repo_list_envelope(messages)
    if envelope is None:
        return None
    return format_github_repo_list_reply(envelope)


def is_github_issue_list_intent(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    matched = matches_manifest_intent(text, kind="issue_list", server_id="github")
    if not matched and not _GITHUB_ISSUE_LIST_INTENT.search(raw):
        return False
    if is_github_repo_list_intent(raw):
        return False
    return bool(re.search(r"[\w.-]+", raw))


def parse_github_issue_list_tool_content(content: str) -> dict[str, Any] | None:
    text = str(content or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("code") != "MCP_OK":
        return None
    if "issue_count" not in payload and "issues" not in payload:
        return None
    if "issue_count" not in payload and isinstance(payload.get("issues"), list):
        payload["issue_count"] = len(payload["issues"])
    issues = payload.get("issues")
    if not str(payload.get("summary") or "").strip() and isinstance(issues, list):
        from butler.mcp.result_slim import render_github_issue_list_summary

        payload["summary"] = render_github_issue_list_summary(issues)
    return payload


def find_latest_github_issue_list_envelope(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        envelope = parse_github_issue_list_tool_content(str(msg.get("content") or ""))
        if envelope is not None:
            return envelope
    return None


def format_github_issue_list_reply(envelope: dict[str, Any]) -> str:
    count = int(envelope.get("issue_count") or 0)
    owner = str(envelope.get("owner") or "").strip()
    repo = str(envelope.get("repo") or "").strip()
    state = str(envelope.get("state") or "open").strip()
    full = f"{owner}/{repo}" if owner and repo else (repo or owner or "仓库")
    if count == 0:
        return f"主公，**{full}** 当前没有 {state} issues（共 0 条）。"
    summary = str(envelope.get("summary") or "").strip()
    return f"主公，**{full}** 共有 {count} 条 {state} issues：\n\n{summary}"


def try_github_issue_list_direct_reply(
    messages: list[dict[str, Any]],
    *,
    user_text: str,
) -> str | None:
    if not github_issue_list_direct_enabled():
        return None
    if not is_github_issue_list_intent(user_text):
        return None
    envelope = find_latest_github_issue_list_envelope(messages)
    if envelope is None:
        return None
    return format_github_issue_list_reply(envelope)


def try_handle_github_issues_intent(user_text: str) -> str | None:
    """Gateway shortcut: fetch issues via MCP without LLM."""
    if not github_issue_list_direct_enabled():
        return None
    if not is_github_issue_list_intent(user_text):
        return None
    from butler.mcp.github_tool_aliases import normalize_github_mcp_args, parse_github_owner_repo
    from butler.mcp.registry_hook import dispatch_mcp_tool

    owner, repo = parse_github_owner_repo(user_text, {})
    if not repo:
        return None
    args = normalize_github_mcp_args(
        "mcp_github_lst_repo_issues",
        {"owner": owner, "repo": repo},
        user_text=user_text,
    )
    raw = dispatch_mcp_tool("mcp_github_lst_repo_issues", args)
    if not raw:
        return None
    envelope = parse_github_issue_list_tool_content(raw)
    if envelope is None:
        return None
    if owner:
        envelope["owner"] = owner
    if repo:
        envelope["repo"] = repo
    envelope["state"] = args.get("state", "open")
    if not envelope.get("summary") and int(envelope.get("issue_count") or 0) == 0:
        envelope["summary"] = "（无匹配 issues）"
    return format_github_issue_list_reply(envelope)
