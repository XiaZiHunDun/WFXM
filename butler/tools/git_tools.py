"""Git operation tools for the DevAgent.

v2 upgrade: full diff output, git_log, git_branch, separate git_add / git_commit.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from butler.tools.registry import register_tool

_MAX_OUTPUT = 30_000


async def _run_git(args: list[str], cwd: str = "") -> dict:
    cwd_path = Path(cwd) if cwd else _get_project_root()
    cmd = ["git"] + args

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
        truncated = len(out) > _MAX_OUTPUT
        out = out[:_MAX_OUTPUT]
        result = {"exit_code": proc.returncode, "stdout": out, "stderr": err}
        if truncated:
            result["truncated"] = True
        return result
    except asyncio.TimeoutError:
        return {"error": "Git 命令超时"}
    except FileNotFoundError:
        return {"error": "git 未安装"}


def _get_project_root() -> Path:
    from butler.core.project_manager import project_manager
    if project_manager.current_project:
        proj = project_manager.get_project(project_manager.current_project)
        if proj:
            return proj.workspace
    return Path.cwd()


# --- git_status ---

@register_tool(
    name="git_status",
    description="查看当前项目的 git 状态（已修改/暂存/未跟踪的文件）",
    parameters={
        "type": "object",
        "properties": {
            "cwd": {"type": "string", "description": "工作目录（可选）"},
        },
        "required": [],
    },
    is_async=True,
    category="git",
)
async def git_status(cwd: str = "") -> dict:
    return await _run_git(["status", "--short", "--branch"], cwd)


# --- git_diff (full diff output) ---

@register_tool(
    name="git_diff",
    description="查看文件改动的完整 diff 内容。默认显示工作区未暂存的改动。",
    parameters={
        "type": "object",
        "properties": {
            "staged": {"type": "boolean", "description": "是否只看暂存区的改动，默认 false"},
            "stat_only": {"type": "boolean", "description": "只显示统计摘要，默认 false"},
            "file": {"type": "string", "description": "指定文件路径（可选，默认全部）"},
            "ref": {"type": "string", "description": "对比的 ref（如 HEAD~3、main），默认为工作区"},
            "cwd": {"type": "string", "description": "工作目录（可选）"},
        },
        "required": [],
    },
    is_async=True,
    category="git",
)
async def git_diff(
    staged: bool = False,
    stat_only: bool = False,
    file: str = "",
    ref: str = "",
    cwd: str = "",
) -> dict:
    args = ["diff"]
    if staged:
        args.append("--cached")
    if stat_only:
        args.append("--stat")
    if ref:
        args.append(ref)
    if file:
        args.extend(["--", file])
    return await _run_git(args, cwd)


# --- git_log ---

@register_tool(
    name="git_log",
    description="查看 git 提交历史",
    parameters={
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "显示的提交数量，默认 10"},
            "oneline": {"type": "boolean", "description": "单行格式，默认 true"},
            "file": {"type": "string", "description": "只看指定文件的历史（可选）"},
            "author": {"type": "string", "description": "按作者过滤（可选）"},
            "since": {"type": "string", "description": "起始时间，如 '2024-01-01'（可选）"},
            "cwd": {"type": "string", "description": "工作目录（可选）"},
        },
        "required": [],
    },
    is_async=True,
    category="git",
)
async def git_log(
    count: int = 10,
    oneline: bool = True,
    file: str = "",
    author: str = "",
    since: str = "",
    cwd: str = "",
) -> dict:
    args = ["log", f"-{count}"]
    if oneline:
        args.append("--oneline")
    else:
        args.extend(["--format=%H %an %ad %s", "--date=short"])
    if author:
        args.append(f"--author={author}")
    if since:
        args.append(f"--since={since}")
    if file:
        args.extend(["--", file])
    return await _run_git(args, cwd)


# --- git_add (separate from commit) ---

@register_tool(
    name="git_add",
    description="将文件添加到 git 暂存区",
    parameters={
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要暂存的文件列表。使用 ['.'] 暂存所有改动。",
            },
            "cwd": {"type": "string", "description": "工作目录（可选）"},
        },
        "required": ["files"],
    },
    is_async=True,
    category="git",
)
async def git_add(files: list[str], cwd: str = "") -> dict:
    if not files:
        return {"error": "请指定要暂存的文件"}
    return await _run_git(["add"] + files, cwd)


# --- git_commit (no longer auto-adds) ---

@register_tool(
    name="git_commit",
    description="提交暂存区的改动。注意：需要先用 git_add 暂存文件。",
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "提交信息"},
            "cwd": {"type": "string", "description": "工作目录（可选）"},
        },
        "required": ["message"],
    },
    is_async=True,
    category="git",
)
async def git_commit(message: str, cwd: str = "") -> dict:
    return await _run_git(["commit", "-m", message], cwd)


# --- git_branch ---

@register_tool(
    name="git_branch",
    description="管理 git 分支：列出、创建、切换、删除",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "create", "switch", "delete"],
                "description": "操作类型：list 列出分支，create 创建，switch 切换，delete 删除",
            },
            "name": {"type": "string", "description": "分支名称（create/switch/delete 时必填）"},
            "cwd": {"type": "string", "description": "工作目录（可选）"},
        },
        "required": ["action"],
    },
    is_async=True,
    category="git",
)
async def git_branch(action: str, name: str = "", cwd: str = "") -> dict:
    if action == "list":
        return await _run_git(["branch", "-a", "--sort=-committerdate"], cwd)
    elif action == "create":
        if not name:
            return {"error": "创建分支需要指定名称"}
        return await _run_git(["checkout", "-b", name], cwd)
    elif action == "switch":
        if not name:
            return {"error": "切换分支需要指定名称"}
        return await _run_git(["checkout", name], cwd)
    elif action == "delete":
        if not name:
            return {"error": "删除分支需要指定名称"}
        return await _run_git(["branch", "-d", name], cwd)
    else:
        return {"error": f"未知操作: {action}，支持 list/create/switch/delete"}
