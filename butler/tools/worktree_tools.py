"""Git worktree helpers for isolated parallel agent workspaces."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from butler.tools.registry import register_tool

logger = logging.getLogger(__name__)


class WorktreeManager:
    """Manages git worktrees for parallel agent isolation."""

    WORKTREE_PREFIX = "butler-agent"

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self._worktrees: dict[str, Path] = {}

    async def _run_git(
        self, args: list[str], cwd: str | Path | None = None
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd or self.repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    async def create_worktree(
        self, task_id: str, base_branch: str = "HEAD"
    ) -> Optional[str]:
        """Create an isolated worktree for an agent task. Returns worktree path or None."""
        branch_name = f"{self.WORKTREE_PREFIX}-{task_id}"
        worktree_parent = self.repo_root.parent / ".butler-worktrees"
        worktree_parent.mkdir(parents=True, exist_ok=True)
        worktree_path = worktree_parent / branch_name

        if worktree_path.exists():
            self._worktrees[task_id] = worktree_path
            return str(worktree_path)

        rc, _out, err = await self._run_git(
            ["worktree", "add", "-b", branch_name, str(worktree_path), base_branch]
        )

        if rc != 0:
            logger.error("Failed to create worktree: %s", err)
            return None

        self._worktrees[task_id] = worktree_path
        logger.info("Created worktree for task %s: %s", task_id, worktree_path)
        return str(worktree_path)

    async def remove_worktree(self, task_id: str, force: bool = False) -> bool:
        """Remove a worktree after task completion."""
        branch_name = f"{self.WORKTREE_PREFIX}-{task_id}"
        worktree_path = self._worktrees.get(task_id)

        if not worktree_path:
            worktree_parent = self.repo_root.parent / ".butler-worktrees"
            worktree_path = worktree_parent / branch_name

        if not worktree_path.exists():
            self._worktrees.pop(task_id, None)
            return True

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(worktree_path))

        rc, _out, err = await self._run_git(args)
        if rc != 0:
            logger.error("Failed to remove worktree: %s", err)
            return False

        self._worktrees.pop(task_id, None)

        await self._run_git(["branch", "-D", branch_name])
        return True

    async def list_worktrees(self) -> list[dict]:
        """List all butler-managed worktrees."""
        rc, out, _err = await self._run_git(["worktree", "list", "--porcelain"])
        if rc != 0:
            return []

        worktrees: list[dict] = []
        current: dict = {}
        for line in out.splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line.split(" ", 1)[1]}
            elif line.startswith("HEAD "):
                current["head"] = line.split(" ", 1)[1]
            elif line.startswith("branch "):
                current["branch"] = line.split(" ", 1)[1]
            elif line == "bare":
                current["bare"] = True
        if current:
            worktrees.append(current)

        def _is_managed(w: dict) -> bool:
            br = w.get("branch", "") or ""
            pth = w.get("path", "") or ""
            return self.WORKTREE_PREFIX in br or self.WORKTREE_PREFIX in pth

        return [w for w in worktrees if _is_managed(w)]

    async def merge_worktree(self, task_id: str, target_branch: str = "") -> dict:
        """Merge worktree branch back to target branch with conflict detection."""
        branch_name = f"{self.WORKTREE_PREFIX}-{task_id}"
        if not target_branch:
            rc, out, _err = await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
            target_branch = out.strip() or "main"

        # Pre-merge: check for conflicts using merge --no-commit --no-ff
        rc, _out, err = await self._run_git(["checkout", target_branch])
        if rc != 0:
            return {
                "success": False,
                "error": f"Checkout failed: {err}",
                "branch": branch_name,
            }

        # Dry-run merge to detect conflicts
        rc, out, err = await self._run_git(
            ["merge", "--no-commit", "--no-ff", branch_name]
        )

        if rc != 0:
            # Conflict detected — collect conflict info
            await self._run_git(["merge", "--abort"])
            conflict_files = await self._get_conflict_files(branch_name, target_branch)
            diff_stat = await self._get_diff_stat(branch_name, target_branch)
            return {
                "success": False,
                "has_conflicts": True,
                "conflict_files": conflict_files,
                "diff_stat": diff_stat,
                "error": (
                    f"合并 {branch_name} → {target_branch} 存在冲突。"
                    f"冲突文件: {', '.join(conflict_files)}。"
                    f"请手动解决冲突或委托 ReviewAgent 处理。"
                ),
                "branch": branch_name,
                "suggestion": "使用 worktree_diff 查看具体差异，或在 worktree 中修复冲突后重新合并",
            }

        # No conflicts — complete the merge
        rc, out, err = await self._run_git(
            ["commit", "-m", f"Merge {branch_name} into {target_branch}"]
        )

        if rc != 0:
            # Nothing to commit (identical content)
            await self._run_git(["merge", "--abort"])
            return {
                "success": True,
                "branch": branch_name,
                "merged_into": target_branch,
                "output": "分支内容一致，无需合并",
            }

        return {
            "success": True,
            "branch": branch_name,
            "merged_into": target_branch,
            "output": out.strip(),
        }

    async def _get_conflict_files(self, branch: str, target: str) -> list[str]:
        """Get list of files that would conflict."""
        rc, out, _err = await self._run_git(
            ["diff", "--name-only", f"{target}...{branch}"]
        )
        if rc != 0:
            return []
        changed_in_branch = set(out.strip().splitlines())

        rc, out, _err = await self._run_git(
            ["diff", "--name-only", f"{branch}...{target}"]
        )
        if rc != 0:
            return []
        changed_in_target = set(out.strip().splitlines())

        return sorted(changed_in_branch & changed_in_target)

    async def _get_diff_stat(self, branch: str, target: str) -> str:
        """Get diff stat between branch and target."""
        rc, out, _err = await self._run_git(
            ["diff", "--stat", f"{target}...{branch}"]
        )
        return out.strip() if rc == 0 else ""

    def get_worktree_path(self, task_id: str) -> Optional[str]:
        """Get the worktree path for a task."""
        wt = self._worktrees.get(task_id)
        if wt and wt.exists():
            return str(wt)
        return None


_manager: WorktreeManager | None = None


def _get_manager() -> WorktreeManager:
    global _manager
    if _manager is None:
        from butler.core.project_manager import project_manager

        proj = project_manager.get_current()
        root = proj.workspace if proj else Path.cwd()
        _manager = WorktreeManager(root)
    return _manager


@register_tool(
    name="worktree_create",
    description="创建隔离的 git worktree，用于并行 Agent 任务执行",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务 ID"},
            "base_branch": {
                "type": "string",
                "description": "基于哪个分支创建（默认 HEAD）",
            },
        },
        "required": ["task_id"],
    },
    is_async=True,
    category="git",
)
async def worktree_create(task_id: str, base_branch: str = "HEAD") -> dict:
    mgr = _get_manager()
    path = await mgr.create_worktree(task_id, base_branch)
    if path:
        return {"success": True, "worktree_path": path, "task_id": task_id}
    return {"error": "创建 worktree 失败"}


@register_tool(
    name="worktree_remove",
    description="删除已完成任务的 git worktree",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务 ID"},
        },
        "required": ["task_id"],
    },
    is_async=True,
    category="git",
)
async def worktree_remove(task_id: str) -> dict:
    mgr = _get_manager()
    ok = await mgr.remove_worktree(task_id)
    return {"success": ok, "task_id": task_id}


@register_tool(
    name="worktree_list",
    description="列出所有 Butler 管理的 git worktree",
    parameters={"type": "object", "properties": {}},
    is_async=True,
    category="git",
)
async def worktree_list() -> dict:
    mgr = _get_manager()
    wts = await mgr.list_worktrees()
    return {"worktrees": wts}


@register_tool(
    name="worktree_merge",
    description="将 worktree 分支合并回主分支",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务 ID"},
            "target_branch": {
                "type": "string",
                "description": "目标分支（默认当前分支）",
            },
        },
        "required": ["task_id"],
    },
    is_async=True,
    category="git",
)
async def worktree_merge(task_id: str, target_branch: str = "") -> dict:
    mgr = _get_manager()
    return await mgr.merge_worktree(task_id, target_branch)


@register_tool(
    name="worktree_diff",
    description="查看 worktree 分支与目标分支的差异",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务 ID"},
            "target_branch": {
                "type": "string",
                "description": "目标分支（默认当前分支）",
            },
        },
        "required": ["task_id"],
    },
    is_async=True,
    category="git",
)
async def worktree_diff(task_id: str, target_branch: str = "") -> dict:
    mgr = _get_manager()
    branch_name = f"{mgr.WORKTREE_PREFIX}-{task_id}"
    if not target_branch:
        rc, out, _err = await mgr._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        target_branch = out.strip() or "main"
    rc, out, _err = await mgr._run_git(["diff", f"{target_branch}...{branch_name}"])
    if rc != 0:
        return {"error": f"无法获取差异: {_err}"}
    from butler.tools.output_limits import truncate_output

    return {"diff": truncate_output(out), "branch": branch_name, "target": target_branch}
