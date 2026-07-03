"""Resolve common LLM mis-names for GitHub MCP tools (EXT-4)."""

from __future__ import annotations

import os
import re
from typing import Any

_GITHUB_TOOL_ALIASES: dict[str, str] = {
    "mcp_github_get_issues": "mcp_github_lst_repo_issues",
    "mcp_github_list_issues": "mcp_github_lst_repo_issues",
    "mcp_github_list_repo_issues": "mcp_github_lst_repo_issues",
    "mcp_github_get_repository_issues": "mcp_github_lst_repo_issues",
    "mcp_github_list_repos": "mcp_github_lst_repos_authenticated_usr",
    "mcp_github_list_repositories": "mcp_github_lst_repos_authenticated_usr",
}


def resolve_github_mcp_tool_name(name: str) -> str:
    key = str(name or "").strip()
    if key in _GITHUB_TOOL_ALIASES:
        return _GITHUB_TOOL_ALIASES[key]
    from butler.mcp.github_tool_aliases_ops import resolve_mcp_tool_alias_safe

    resolved = resolve_mcp_tool_alias_safe(key)
    if resolved != key:
        return resolved
    return key


def default_github_owner() -> str:
    return os.getenv("BUTLER_GITHUB_DEFAULT_OWNER", "XiaZiHunDun").strip() or "XiaZiHunDun"


def parse_github_owner_repo(
    text: str,
    args: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Best-effort owner/repo from tool args or user text."""
    raw_args = dict(args or {})
    owner = str(raw_args.get("owner") or "").strip()
    repo = str(raw_args.get("repo") or raw_args.get("repository") or "").strip()
    if owner and repo:
        return owner, repo
    if repo and "/" in repo:
        left, right = repo.split("/", 1)
        return left.strip(), right.strip()
    user_text = str(text or "").strip()
    slash = re.search(r"([\w.-]+)/([\w.-]+)", user_text)
    if slash:
        return slash.group(1), slash.group(2)
    if not repo:
        m = re.search(
            r"(?:列出|list|查看|查|看看)\s*([\w.-]+)\s*的\s*issues?",
            user_text,
            re.IGNORECASE,
        )
        if m:
            repo = m.group(1)
        else:
            m2 = re.search(r"\b([\w.-]+)\s*的\s*issues?\b", user_text, re.IGNORECASE)
            if m2:
                repo = m2.group(1)
    if not owner:
        owner = default_github_owner()
    return owner, repo


def normalize_github_mcp_args(
    tool_name: str,
    args: dict[str, Any],
    *,
    user_text: str = "",
) -> dict[str, Any]:
    out = dict(args or {})
    resolved = resolve_github_mcp_tool_name(tool_name)
    if resolved == "mcp_github_lst_repo_issues":
        owner, repo = parse_github_owner_repo(user_text, out)
        if owner:
            out["owner"] = owner
        if repo:
            out["repo"] = repo
        out.pop("repository", None)
        state = str(out.get("state") or "").strip().lower()
        if not state:
            if any(k in str(user_text or "") for k in ("全部", "所有", "all", "关闭", "closed")):
                out["state"] = "all" if any(k in str(user_text or "").lower() for k in ("全部", "所有", "all")) else "closed"
            else:
                out["state"] = "open"
    return out
