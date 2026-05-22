"""WeChat slash commands for dev-tool visibility and optional smoke."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _env_on(name: str) -> bool:
    from butler.env_parse import env_truthy

    return env_truthy(name)


def format_dev_status() -> str:
    lines = [
        "开发工具状态（当前网关进程环境）",
        f"  BUTLER_ENABLE_TERMINAL={os.getenv('BUTLER_ENABLE_TERMINAL', '0')}",
        f"  BUTLER_TERMINAL_PROFILE={os.getenv('BUTLER_TERMINAL_PROFILE', '(默认)')}",
        f"  BUTLER_ENABLE_GIT={os.getenv('BUTLER_ENABLE_GIT', '0')}",
        f"  BUTLER_ENABLE_GIT_WRITE={os.getenv('BUTLER_ENABLE_GIT_WRITE', '0')}",
        f"  BUTLER_TOOL_SAFE_ROOT={os.getenv('BUTLER_TOOL_SAFE_ROOT', '(未设)')}",
        f"  BUTLER_WECHAT_DEV_SMOKE={os.getenv('BUTLER_WECHAT_DEV_SMOKE', '0')}",
        "",
        "生产微信建议: GIT_WRITE=0；本机验收可开 GIT_WRITE=1。",
        "跑守门测试: 设 BUTLER_WECHAT_DEV_SMOKE=1 后发送 /开发验收",
        "或 SSH: bash scripts/butler-dev-delegate-smoke.sh",
    ]
    return "\n".join(lines)


def run_dev_smoke(*, timeout_seconds: int = 180) -> str:
    if not _env_on("BUTLER_WECHAT_DEV_SMOKE"):
        return (
            "未启用微信开发验收（BUTLER_WECHAT_DEV_SMOKE=0）。\n"
            "在 .env 设 BUTLER_WECHAT_DEV_SMOKE=1 并重启网关后重试，"
            "或在本机执行: bash scripts/butler-dev-delegate-smoke.sh"
        )
    root = _repo_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{root}:{env.get('PYTHONPATH', '')}"
    env.setdefault("BUTLER_ENABLE_TERMINAL", "1")
    env.setdefault("BUTLER_TERMINAL_PROFILE", "dev")
    env.setdefault("BUTLER_ENABLE_GIT", "1")
    env.setdefault("BUTLER_ENABLE_GIT_WRITE", "1")
    try:
        proc = subprocess.run(
            [
                "python3",
                "-m",
                "pytest",
                "tests/test_dev_tools_integration.py",
                "-q",
                "--tb=line",
            ],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=max(30, timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"开发验收超时（>{timeout_seconds}s）"
    except OSError as exc:
        return f"开发验收启动失败: {exc}"

    tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-400:]
    if proc.returncode == 0:
        return "开发验收通过（test_dev_tools_integration）。\n" + tail.strip()
    return (
        f"开发验收失败 exit={proc.returncode}。\n"
        + tail.strip()
        + "\n\n详见 logs 或本机 butler-dev-delegate-smoke.sh"
    )


def handle_dev_command(cmd: str, arg: str = "") -> str | None:
    """Return reply for /开发状态 /开发验收 or None."""
    del arg
    if cmd in ("/开发状态", "/dev-status"):
        return format_dev_status()
    if cmd in ("/开发验收", "/dev-smoke"):
        return run_dev_smoke()
    return None
