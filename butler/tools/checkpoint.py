#!/usr/bin/env python3
"""Simple git-stash based checkpoint / rollback for agent work."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CHECKPOINT_BRANCH_PREFIX = "butler-checkpoint"


class CheckpointManager:
    def __init__(self, working_dir: str | Path):
        self.working_dir = Path(working_dir)
        self._last_checkpoint_ts: float = 0.0
        self._checkpoint_count: int = 0
        self._min_interval: float = 30.0  # minimum seconds between checkpoints

    def should_checkpoint(self) -> bool:
        """Rate-limit checkpoints to min_interval."""
        if self._last_checkpoint_ts <= 0.0:
            return True
        return time.time() - self._last_checkpoint_ts >= self._min_interval

    async def _run_git(self, args: list[str]) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(self.working_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out_b, err_b = await proc.communicate()
        stdout = out_b.decode("utf-8", errors="replace")
        stderr = err_b.decode("utf-8", errors="replace")
        code = proc.returncode if proc.returncode is not None else -1
        return code, stdout, stderr

    async def create_checkpoint(self, label: str = "") -> Optional[str]:
        """Create a git stash checkpoint. Returns checkpoint ID or None on failure."""
        if not self.should_checkpoint():
            logger.info("create_checkpoint skipped: rate limited")
            return None

        ts = int(time.time())
        self._checkpoint_count += 1
        msg = f"{_CHECKPOINT_BRANCH_PREFIX}: {label} {ts}".strip()

        code, stdout, stderr = await self._run_git(
            ["stash", "push", "-u", "-m", msg]
        )
        if code != 0:
            logger.warning("git stash push failed (%s): %s", code, stderr or stdout)
            self._checkpoint_count -= 1
            return None

        self._last_checkpoint_ts = time.time()
        entry = (stderr or stdout or "").strip() or msg
        logger.info("Checkpoint created: %s", entry)
        return f"{self._checkpoint_count}:{msg}"

    async def rollback_last(self) -> dict:
        """Rollback to the last checkpoint via git stash pop."""
        code, stdout, stderr = await self._run_git(["stash", "pop"])
        ok = code == 0
        return {
            "success": ok,
            "stdout": stdout,
            "stderr": stderr,
            "message": "stash pop completed" if ok else "stash pop failed",
        }

    async def list_checkpoints(self) -> list[dict]:
        """List available checkpoints."""
        code, stdout, stderr = await self._run_git(["stash", "list"])
        if code != 0:
            logger.warning("git stash list failed: %s", stderr)
            return []

        entries: list[dict] = []
        for line in stdout.splitlines():
            if _CHECKPOINT_BRANCH_PREFIX not in line:
                continue
            parts = line.split(":", 2)
            stash_id = parts[0].strip() if parts else line
            desc = parts[2].strip() if len(parts) > 2 else line
            entries.append({"stash": stash_id, "description": desc, "raw": line})
        return entries
