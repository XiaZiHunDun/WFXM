"""Shell execution tools for the Butler."""

from __future__ import annotations

import asyncio
import subprocess

from butler.tools.command_safety import check_and_log
from butler.tools.output_limits import truncate_output
from butler.tools.registry import register_tool


@register_tool(
    name="run_shell",
    description="在指定目录中执行 shell 命令并返回输出",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
            "cwd": {"type": "string", "description": "工作目录（可选，默认为当前项目目录）"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 60"},
        },
        "required": ["command"],
    },
    is_async=True,
    category="shell",
)
async def run_shell(command: str, cwd: str = "", timeout: int = 60) -> dict:
    safety = check_and_log(command)
    if safety.is_dangerous:
        return {
            "error": f"危险命令被拦截: {safety.description} (类型: {safety.category})",
            "command": command,
            "blocked": True,
        }

    if not cwd:
        from butler.core.project_manager import project_manager
        if project_manager.current_project:
            proj = project_manager.get_project(project_manager.current_project)
            if proj:
                cwd = str(proj.workspace)
    cwd = cwd or "."

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout_text, _ = truncate_output(stdout.decode("utf-8", errors="replace"))
        stderr_text, _ = truncate_output(stderr.decode("utf-8", errors="replace"))

        return {
            "exit_code": proc.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "command": command,
            "cwd": cwd,
        }
    except asyncio.TimeoutError:
        return {"error": f"命令超时（{timeout}秒）", "command": command}
    except Exception as e:
        return {"error": str(e), "command": command}
