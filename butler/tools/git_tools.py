"""Git tools for Butler v4 — workspace-scoped, opt-in, no network subcommands."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from butler.tools.path_safety import check_tool_path, default_tool_workdir, safe_subprocess_env

logger = logging.getLogger(__name__)

_MAX_GIT_OUTPUT = 30_000
_GIT_TIMEOUT_SECONDS = 30


def git_read_enabled() -> bool:
    return os.getenv("BUTLER_ENABLE_GIT", "").strip() == "1"


def git_write_enabled() -> bool:
    return (
        git_read_enabled()
        and os.getenv("BUTLER_ENABLE_GIT_WRITE", "").strip() == "1"
    )


def _disabled_read_msg() -> str:
    return json.dumps({
        "error": "Git tools are disabled. Set BUTLER_ENABLE_GIT=1 in .env.",
        "code": "GIT_DISABLED",
    })


def _disabled_write_msg() -> str:
    return json.dumps({
        "error": "Git write tools require BUTLER_ENABLE_GIT_WRITE=1 (and BUTLER_ENABLE_GIT=1).",
        "code": "GIT_WRITE_DISABLED",
    })


def _resolve_git_workdir(workdir: str | None) -> tuple[Path | None, str | None]:
    if workdir and str(workdir).strip():
        safety = check_tool_path(workdir)
    else:
        safety = default_tool_workdir()
    if not safety.allowed:
        return None, safety.error
    if not safety.path.is_dir():
        return None, f"Not a directory: {workdir or safety.path}"
    return safety.path, None


def _run_git(args: list[str], *, workdir: str | None = None) -> dict[str, Any]:
    cwd, err = _resolve_git_workdir(workdir)
    if err:
        return {"error": err, "exit_code": -1}
    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=safe_subprocess_env(),
        )
    except subprocess.TimeoutExpired:
        return {"error": "Git command timed out", "exit_code": -1}
    except FileNotFoundError:
        return {"error": "git executable not found", "exit_code": -1}
    except OSError as exc:
        return {"error": str(exc), "exit_code": -1}

    out = (proc.stdout or "")[:_MAX_GIT_OUTPUT]
    err_text = (proc.stderr or "")[:_MAX_GIT_OUTPUT]
    payload: dict[str, Any] = {
        "exit_code": proc.returncode,
        "stdout": out,
        "stderr": err_text,
        "cwd": str(cwd),
    }
    if len(proc.stdout or "") > _MAX_GIT_OUTPUT:
        payload["truncated"] = True
    return payload


def _tool_git_status(workdir: str | None = None, **_) -> str:
    if not git_read_enabled():
        return _disabled_read_msg()
    return json.dumps(_run_git(["status", "--short", "--branch"], workdir=workdir))


def _tool_git_diff(
    staged: bool = False,
    stat_only: bool = False,
    file: str = "",
    ref: str = "",
    workdir: str | None = None,
    **_,
) -> str:
    if not git_read_enabled():
        return _disabled_read_msg()
    args = ["diff"]
    if staged:
        args.append("--cached")
    if stat_only:
        args.append("--stat")
    if ref:
        args.append(ref)
    if file:
        if (check := check_tool_path(file)).allowed:
            args.extend(["--", str(check.path)])
        else:
            return json.dumps({"error": check.error, "exit_code": -1})
    return json.dumps(_run_git(args, workdir=workdir))


def _tool_git_log(
    count: int = 10,
    oneline: bool = True,
    file: str = "",
    author: str = "",
    since: str = "",
    workdir: str | None = None,
    **_,
) -> str:
    if not git_read_enabled():
        return _disabled_read_msg()
    try:
        n = max(1, min(int(count), 100))
    except (TypeError, ValueError):
        return json.dumps({"error": "count must be an integer", "exit_code": -1})
    args = ["log", f"-{n}"]
    if oneline:
        args.append("--oneline")
    else:
        args.extend(["--format=%H %an %ad %s", "--date=short"])
    if author:
        args.append(f"--author={author}")
    if since:
        args.append(f"--since={since}")
    if file:
        if (check := check_tool_path(file)).allowed:
            args.extend(["--", str(check.path)])
        else:
            return json.dumps({"error": check.error, "exit_code": -1})
    return json.dumps(_run_git(args, workdir=workdir))


def _tool_git_branch(
    action: str = "list",
    name: str = "",
    workdir: str | None = None,
    **_,
) -> str:
    act = (action or "list").strip().lower()
    if act == "list":
        if not git_read_enabled():
            return _disabled_read_msg()
        return json.dumps(
            _run_git(["branch", "-a", "--sort=-committerdate"], workdir=workdir)
        )
    if not git_write_enabled():
        return _disabled_write_msg()
    if act == "create":
        if not name.strip():
            return json.dumps({"error": "branch name required for create", "exit_code": -1})
        return json.dumps(_run_git(["checkout", "-b", name.strip()], workdir=workdir))
    if act == "switch":
        if not name.strip():
            return json.dumps({"error": "branch name required for switch", "exit_code": -1})
        return json.dumps(_run_git(["checkout", name.strip()], workdir=workdir))
    if act == "delete":
        if not name.strip():
            return json.dumps({"error": "branch name required for delete", "exit_code": -1})
        return json.dumps(_run_git(["branch", "-d", name.strip()], workdir=workdir))
    return json.dumps({"error": f"Unknown action: {action}", "exit_code": -1})


def _tool_git_add(files: list | None = None, workdir: str | None = None, **_) -> str:
    if not git_write_enabled():
        return _disabled_write_msg()
    paths = list(files or [])
    if not paths:
        return json.dumps({"error": "files list is required", "exit_code": -1})
    argv = ["add"]
    for raw in paths:
        token = str(raw).strip()
        if token == ".":
            argv.append(".")
            continue
        check = check_tool_path(token)
        if not check.allowed:
            return json.dumps({"error": check.error, "exit_code": -1})
        argv.append(str(check.path))
    return json.dumps(_run_git(argv, workdir=workdir))


def _tool_git_commit(message: str = "", workdir: str | None = None, **_) -> str:
    if not git_write_enabled():
        return _disabled_write_msg()
    msg = (message or "").strip()
    if not msg:
        return json.dumps({"error": "commit message is required", "exit_code": -1})
    return json.dumps(_run_git(["commit", "-m", msg], workdir=workdir))


def _tool_git_push(
    remote: str = "origin",
    branch: str = "",
    force: bool = False,
    workdir: str | None = None,
    **_,
) -> str:
    """Push to remote — requires BUTLER_ENABLE_GIT_PUSH=1 and Owner approval."""
    if not git_write_enabled():
        return _disabled_write_msg()
    push_enabled = os.getenv("BUTLER_ENABLE_GIT_PUSH", "").strip() == "1"
    if not push_enabled:
        return json.dumps({
            "error": "Git push requires BUTLER_ENABLE_GIT_PUSH=1 in .env.",
            "code": "GIT_PUSH_DISABLED",
        })
    if force:
        return json.dumps({
            "error": "Force push is blocked for safety. Use manual git push --force.",
            "code": "GIT_FORCE_PUSH_BLOCKED",
        })

    cwd, err = _resolve_git_workdir(workdir)
    if err:
        return json.dumps({"error": err, "exit_code": -1})

    remote_name = (remote or "origin").strip()
    branch_name = (branch or "").strip()
    if not branch_name:
        result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], workdir=workdir)
        branch_name = (result.get("stdout") or "").strip()
        if not branch_name:
            return json.dumps({"error": "Cannot detect current branch", "exit_code": -1})

    if branch_name in ("main", "master"):
        return json.dumps({
            "error": f"Push to protected branch '{branch_name}' is blocked.",
            "code": "GIT_PROTECTED_BRANCH",
        })

    approval_key = f"git_push:{remote_name}:{branch_name}"
    try:
        from butler.tools.terminal_approval import check_approval

        approved = check_approval(approval_key)
        if not approved:
            return json.dumps({
                "ok": False,
                "code": "PUSH_REQUIRES_APPROVAL",
                "error": (
                    f"Git push to {remote_name}/{branch_name} requires Owner approval.\n"
                    f"请在微信确认：/批准一次 git_push 或 /始终允许 git_push"
                ),
                "remote": remote_name,
                "branch": branch_name,
            })
    except ImportError:
        pass

    args = ["push", remote_name, branch_name]
    result = _run_git(args, workdir=workdir)
    return json.dumps(result)


def register_git_tools(register: Callable[..., None]) -> None:
    """Register git_* tools (always visible; gated at runtime by env)."""

    register(
        name="git_status",
        description=(
            "【porcelain·names】Branch plus modified/staged/untracked path buckets. "
            "Filenames only; zero +/- line content."
        ),
        schema={
            "type": "object",
            "properties": {
                "workdir": {"type": "string", "description": "Working directory (optional)"},
            },
        },
        handler=_tool_git_status,
        toolset="git",
    )

    register(
        name="git_diff",
        description=(
            "【unified-patch】+/- line hunks for staged or unstaged changes (stat/ref/file). "
            "Patch text only; zero branch name, zero path inventory table."
        ),
        schema={
            "type": "object",
            "properties": {
                "staged": {"type": "boolean", "description": "Staged diff only", "default": False},
                "stat_only": {"type": "boolean", "description": "Stat summary only", "default": False},
                "file": {"type": "string", "description": "Limit to file path"},
                "ref": {"type": "string", "description": "Compare ref (e.g. HEAD~1)"},
                "workdir": {"type": "string", "description": "Working directory (optional)"},
            },
        },
        handler=_tool_git_diff,
        toolset="git",
    )

    register(
        name="git_log",
        description=(
            "【history·timeline】Recent commits: sha, author, date, subject. "
            "Optional file/author/since filters. No working-tree status, no diff hunks."
        ),
        schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of commits", "default": 10},
                "oneline": {"type": "boolean", "description": "One line per commit", "default": True},
                "file": {"type": "string", "description": "File path filter"},
                "author": {"type": "string", "description": "Author filter"},
                "since": {"type": "string", "description": "Since date"},
                "workdir": {"type": "string", "description": "Working directory (optional)"},
            },
        },
        handler=_tool_git_log,
        toolset="git",
    )

    register(
        name="git_branch",
        description=(
            "List or manage branches. list requires BUTLER_ENABLE_GIT=1; "
            "create/switch/delete require BUTLER_ENABLE_GIT_WRITE=1."
        ),
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "switch", "delete"],
                    "description": "Branch operation",
                },
                "name": {"type": "string", "description": "Branch name (for create/switch/delete)"},
                "workdir": {"type": "string", "description": "Working directory (optional)"},
            },
            "required": ["action"],
        },
        handler=_tool_git_branch,
        toolset="git",
    )

    register(
        name="git_add",
        description=(
            "【stage·index】Put paths into the git index; no commit object is created."
        ),
        schema={
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to stage, or ['.'] for all",
                },
                "workdir": {"type": "string", "description": "Working directory (optional)"},
            },
            "required": ["files"],
        },
        handler=_tool_git_add,
        toolset="git",
    )

    register(
        name="git_commit",
        description=(
            "【snapshot·hash】Finalize the staged index into a new commit with message. "
            "Requires BUTLER_ENABLE_GIT_WRITE=1."
        ),
        schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message"},
                "workdir": {"type": "string", "description": "Working directory (optional)"},
            },
            "required": ["message"],
        },
        handler=_tool_git_commit,
        toolset="git",
    )

    register(
        name="git_push",
        description=(
            "Push commits to remote. Requires BUTLER_ENABLE_GIT_PUSH=1 + Owner approval. "
            "Force push and push to main/master are blocked."
        ),
        schema={
            "type": "object",
            "properties": {
                "remote": {
                    "type": "string",
                    "description": "Remote name (default: origin)",
                    "default": "origin",
                },
                "branch": {
                    "type": "string",
                    "description": "Branch to push (default: current branch)",
                },
                "workdir": {"type": "string", "description": "Working directory (optional)"},
            },
        },
        handler=_tool_git_push,
        toolset="git",
    )
