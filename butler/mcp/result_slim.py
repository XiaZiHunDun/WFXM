"""Compact verbose MCP JSON before tool-result spill (EXT-4 GitHub pilot)."""

from __future__ import annotations

import json
from typing import Any


def slim_mcp_raw_result(text: str, *, tool_name: str, server_id: str) -> str:
    """Return a smaller JSON payload when the MCP body is a known verbose shape."""
    stripped = str(text or "").strip()
    if not stripped:
        return text
    if server_id not in ("github", "todoist"):
        return text
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    original = _tool_tail(tool_name, server_id=server_id)
    norm = original.replace("_", "-")
    if server_id == "github":
        if norm in ("lst-repos-authenticated-usr", "listReposForAuthenticatedUser"):
            slimmed = _slim_repo_list(parsed)
            if slimmed is not None:
                return json.dumps(slimmed, ensure_ascii=False)
        if norm in ("lst-repo-issues", "listRepositoryIssues"):
            slimmed = _slim_issue_list(parsed)
            if slimmed is not None:
                return json.dumps(slimmed, ensure_ascii=False)
        if norm in ("get-authenticated-usr", "getAuthenticatedUser"):
            slimmed = _slim_user(parsed)
            if slimmed is not None:
                return json.dumps(slimmed, ensure_ascii=False)
        if norm in ("get-repo", "getRepository"):
            slimmed = _slim_repo(parsed)
            if slimmed is not None:
                return json.dumps(slimmed, ensure_ascii=False)
    if server_id == "todoist":
        if "lst-project" in norm or "getallproject" in norm.replace("-", ""):
            slimmed = _slim_todoist_project_list(parsed)
            if slimmed is not None:
                return json.dumps(slimmed, ensure_ascii=False)
    return text


def _tool_tail(tool_name: str, *, server_id: str = "") -> str:
    name = str(tool_name or "").strip()
    prefix = f"mcp_{server_id}_" if server_id else "mcp_"
    if server_id and name.startswith(prefix):
        return name[len(prefix) :]
    if name.startswith("mcp_"):
        parts = name.split("_", 2)
        if len(parts) >= 3:
            return parts[2]
    return name


def render_github_repo_list_summary(repos: list[dict[str, Any]]) -> str:
    """WeChat-friendly numbered list from slim repo rows."""
    lines: list[str] = []
    for idx, repo in enumerate(repos, start=1):
        if not isinstance(repo, dict):
            continue
        full_name = str(repo.get("full_name") or repo.get("name") or "").strip()
        if not full_name:
            continue
        short = full_name.split("/", 1)[-1]
        vis = "私有" if repo.get("private") else "公开"
        if repo.get("fork"):
            vis += "，fork"
        lang = str(repo.get("language") or "").strip()
        lang_part = f"，{lang}" if lang else ""
        updated = str(repo.get("updated_at") or "")[:10]
        date_part = f"，更新 {updated}" if updated else ""
        lines.append(f"{idx}. **{short}** — {vis}{lang_part}{date_part}")
    return "\n".join(lines)


def build_github_repo_list_envelope(
    repos: list[dict[str, Any]],
    *,
    tool_name: str,
    server_id: str,
) -> dict[str, Any]:
    summary = render_github_repo_list_summary(repos)
    login = ""
    if repos and isinstance(repos[0], dict):
        owner = repos[0].get("full_name") or ""
        if "/" in str(owner):
            login = str(owner).split("/", 1)[0]
    return {
        "ok": True,
        "tool": tool_name,
        "server": server_id,
        "code": "MCP_OK",
        "repo_count": len(repos),
        "login": login,
        "summary": summary,
        "repos": repos,
    }


def render_todoist_project_list_summary(projects: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for idx, project in enumerate(projects, start=1):
        if not isinstance(project, dict):
            continue
        name = str(project.get("name") or "").strip()
        if not name:
            continue
        color = str(project.get("color") or "").strip()
        color_part = f" ({color})" if color else ""
        lines.append(f"{idx}. **{name}**{color_part}")
    return "\n".join(lines) if lines else "（无项目）"


def build_todoist_project_list_envelope(
    projects: list[dict[str, Any]],
    *,
    tool_name: str,
    server_id: str,
) -> dict[str, Any]:
    summary = render_todoist_project_list_summary(projects)
    return {
        "ok": True,
        "tool": tool_name,
        "server": server_id,
        "code": "MCP_OK",
        "project_count": len(projects),
        "summary": summary,
        "projects": projects,
    }


def _slim_todoist_project_list(parsed: Any) -> list[dict[str, Any]] | None:
    if not isinstance(parsed, list):
        return None
    if parsed and not all(isinstance(item, dict) for item in parsed):
        return None
    if parsed and not any("name" in item for item in parsed if isinstance(item, dict)):
        return None
    out: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "color": item.get("color"),
                "is_favorite": item.get("is_favorite"),
            }
        )
    return out


def _slim_repo_list(parsed: Any) -> list[dict[str, Any]] | None:
    if not isinstance(parsed, list) or not parsed:
        return None
    if not all(isinstance(item, dict) for item in parsed):
        return None
    if not any("full_name" in item or "name" in item for item in parsed):
        return None
    out: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description") or "").strip()
        if len(desc) > 120:
            desc = desc[:117] + "..."
        out.append(
            {
                "full_name": item.get("full_name") or item.get("name"),
                "private": bool(item.get("private")),
                "visibility": item.get("visibility"),
                "fork": bool(item.get("fork")),
                "updated_at": item.get("updated_at") or item.get("pushed_at"),
                "language": item.get("language"),
                "description": desc or None,
            }
        )
    return out


def _slim_issue_list(parsed: Any) -> list[dict[str, Any]] | None:
    if not isinstance(parsed, list):
        return None
    if parsed and not all(isinstance(item, dict) for item in parsed):
        return None
    out: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "number": item.get("number"),
                "title": item.get("title"),
                "state": item.get("state"),
                "html_url": item.get("html_url"),
                "user": (item.get("user") or {}).get("login")
                if isinstance(item.get("user"), dict)
                else None,
            }
        )
    return out


def _slim_user(parsed: Any) -> dict[str, Any] | None:
    if not isinstance(parsed, dict) or "login" not in parsed:
        return None
    return {
        "login": parsed.get("login"),
        "name": parsed.get("name"),
        "html_url": parsed.get("html_url"),
        "public_repos": parsed.get("public_repos"),
        "total_private_repos": parsed.get("total_private_repos"),
    }


def _slim_repo(parsed: Any) -> dict[str, Any] | None:
    if not isinstance(parsed, dict) or "full_name" not in parsed:
        return None
    desc = str(parsed.get("description") or "").strip()
    if len(desc) > 120:
        desc = desc[:117] + "..."
    return {
        "full_name": parsed.get("full_name"),
        "private": bool(parsed.get("private")),
        "visibility": parsed.get("visibility"),
        "fork": bool(parsed.get("fork")),
        "default_branch": parsed.get("default_branch"),
        "open_issues_count": parsed.get("open_issues_count"),
        "updated_at": parsed.get("updated_at"),
        "description": desc or None,
    }


def render_github_issue_list_summary(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "（无匹配 issues）"
    lines: list[str] = []
    for idx, item in enumerate(issues, start=1):
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        title = str(item.get("title") or "").strip() or "(无标题)"
        state = str(item.get("state") or "").strip()
        url = str(item.get("html_url") or "").strip()
        line = f"{idx}. **#{number}** {title}"
        if state:
            line += f" [{state}]"
        if url:
            line += f" — {url}"
        lines.append(line)
    return "\n".join(lines) if lines else "（无匹配 issues）"


def build_github_issue_list_envelope(
    issues: list[dict[str, Any]],
    *,
    tool_name: str,
    server_id: str,
    owner: str = "",
    repo: str = "",
    state: str = "open",
) -> dict[str, Any]:
    summary = render_github_issue_list_summary(issues)
    return {
        "ok": True,
        "tool": tool_name,
        "server": server_id,
        "code": "MCP_OK",
        "issue_count": len(issues),
        "owner": owner,
        "repo": repo,
        "state": state,
        "summary": summary,
        "issues": issues,
    }
