"""Project onboarding git clone best-effort helpers (P0-A)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_clone_repo_safe(
    url: str,
    target_dir: Path,
    *,
    timeout: int,
) -> tuple[bool, str]:
    if target_dir.exists():
        return False, f"目标目录已存在: {target_dir}"
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(target_dir)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "unknown error").strip()
            if len(err) > 300:
                err = err[:300] + "…"
            return False, f"git clone 失败 (exit {result.returncode}): {err}"
        return True, str(target_dir)
    except FileNotFoundError:
        return False, "系统未安装 git，请先安装后重试"
    except subprocess.TimeoutExpired:
        return False, f"git clone 超时 ({timeout}s)，仓库可能过大或网络异常"
    except Exception as exc:
        return False, f"git clone 异常: {exc}"
