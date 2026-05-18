"""Code editing and search tools for the DevAgent.

Key features (v3 upgrade):
- Fuzzy matching: 9 strategies from Hermes (escape-drift + did-you-mean)
- Read state tracking via thread-safe FileStateRegistry
- Post-edit linting: auto-checks syntax after file modification
- Output truncation via output_limits
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import time
from pathlib import Path

from butler.tools.fuzzy_match import fuzzy_replace
from butler.tools.file_state import record_read, note_write, check_stale
from butler.tools.output_limits import truncate_output
from butler.tools.registry import register_tool

_DEFAULT_TASK_ID = "main"


def mark_file_read(path: str, mtime: float | None = None) -> None:
    """Record that a file was read (called from file_tools.read_file)."""
    record_read(_DEFAULT_TASK_ID, path)


def check_read_state(path: str) -> str | None:
    """Check read state before editing. Returns error message or None."""
    return check_stale(_DEFAULT_TASK_ID, str(Path(path).resolve()))


# --- Post-edit linting ---

def _lint_file(path: Path) -> str | None:
    """Run syntax checks based on file extension. Returns error or None."""
    suffix = path.suffix.lower()

    if suffix == ".py":
        return _lint_python(path)
    elif suffix == ".json":
        return _lint_json(path)
    elif suffix in (".yml", ".yaml"):
        return _lint_yaml(path)
    return None


def _lint_python(path: Path) -> str | None:
    try:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        return None
    except SyntaxError as e:
        return f"Python 语法错误 (行 {e.lineno}): {e.msg}"


def _lint_json(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
        json.loads(text)
        return None
    except json.JSONDecodeError as e:
        return f"JSON 语法错误 (行 {e.lineno}): {e.msg}"


def _lint_yaml(path: Path) -> str | None:
    try:
        import yaml
        text = path.read_text(encoding="utf-8")
        yaml.safe_load(text)
        return None
    except ImportError:
        return None
    except Exception as e:
        return f"YAML 语法错误: {e}"


# --- edit_file tool ---

@register_tool(
    name="edit_file",
    description=(
        "替换文件中的指定文本。用 old_text 定位要替换的内容，用 new_text 替换。"
        "支持模糊匹配：当精确匹配失败时，自动尝试空白归一化、缩进归一化、"
        "Unicode 归一化、锚点匹配、上下文匹配等策略。"
        "要求：必须先 read_file 读取目标文件，否则会报错。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "old_text": {"type": "string", "description": "要被替换的原文本"},
            "new_text": {"type": "string", "description": "替换后的新文本"},
        },
        "required": ["path", "old_text", "new_text"],
    },
    category="code",
)
def edit_file(path: str, old_text: str, new_text: str) -> dict:
    resolved = _resolve_path(path)
    if not resolved.exists():
        return {"error": f"文件不存在: {path}"}

    read_err = check_read_state(str(resolved.resolve()))
    if read_err:
        return {"error": read_err}

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"error": f"无法读取（非文本文件）: {path}"}

    new_content, strategy = fuzzy_replace(old_text, new_text, content)
    if new_content is None:
        lines = content.splitlines()
        preview = "\n".join(lines[:20]) if len(lines) > 20 else content
        return {"error": f"{strategy}。文件前 20 行:\n{preview}"}

    resolved.write_text(new_content, encoding="utf-8")

    note_write(_DEFAULT_TASK_ID, str(resolved.resolve()))

    result: dict = {
        "success": True,
        "path": str(resolved),
        "match_strategy": strategy,
        "old_lines": old_text.count("\n") + 1,
        "new_lines": new_text.count("\n") + 1,
    }

    lint_err = _lint_file(resolved)
    if lint_err:
        result["lint_error"] = lint_err
        result["warning"] = "编辑后检测到语法错误，请检查修改是否正确"

    return result


# --- search_code tool ---

@register_tool(
    name="search_code",
    description="在项目中搜索代码（基于 ripgrep）。支持正则表达式、文件类型过滤、上下文行数。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "搜索模式（支持正则表达式）"},
            "path": {"type": "string", "description": "搜索目录（默认当前项目根目录）"},
            "file_glob": {"type": "string", "description": "文件过滤，如 '*.py', '*.ts'"},
            "context_lines": {"type": "integer", "description": "每个匹配显示的上下文行数，默认 2"},
            "max_results": {"type": "integer", "description": "最大结果数，默认 30"},
            "case_insensitive": {"type": "boolean", "description": "是否忽略大小写，默认 false"},
        },
        "required": ["pattern"],
    },
    is_async=True,
    category="code",
)
async def search_code(
    pattern: str,
    path: str = "",
    file_glob: str = "",
    context_lines: int = 2,
    max_results: int = 30,
    case_insensitive: bool = False,
) -> dict:
    search_path = _resolve_path(path) if path else _get_project_root()

    cmd = ["rg", "--line-number", "--no-heading", f"--max-count={max_results}"]
    if context_lines > 0:
        cmd.append(f"-C{context_lines}")
    if file_glob:
        cmd.extend(["-g", file_glob])
    if case_insensitive:
        cmd.append("-i")
    cmd.extend(["--", pattern, str(search_path)])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode("utf-8", errors="replace")

        if proc.returncode == 1:
            return {"matches": 0, "results": "没有找到匹配项"}
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")
            return {"error": f"搜索失败: {err}"}

        lines = output.strip().splitlines()
        truncated_output, was_truncated = truncate_output(output)
        return {
            "matches": len([l for l in lines if not l.startswith("--")]),
            "results": truncated_output,
            "truncated": was_truncated,
        }
    except FileNotFoundError:
        return _fallback_search(pattern, search_path, file_glob, max_results)
    except asyncio.TimeoutError:
        return {"error": "搜索超时"}


def _fallback_search(pattern: str, search_path: Path, file_glob: str, max_results: int) -> dict:
    """Pure Python fallback when ripgrep is not available."""
    import re
    try:
        regex = re.compile(pattern)
    except re.error:
        regex = re.compile(re.escape(pattern))

    results: list[str] = []
    glob_pattern = file_glob if file_glob else "**/*"
    for fp in search_path.glob(glob_pattern):
        if not fp.is_file() or fp.stat().st_size > 1_000_000:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    results.append(f"{fp}:{i}:{line.rstrip()}")
                    if len(results) >= max_results:
                        return {"matches": len(results), "results": "\n".join(results), "fallback": True}
        except Exception:
            continue

    return {"matches": len(results), "results": "\n".join(results) if results else "没有找到匹配项", "fallback": True}


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    from butler.core.project_manager import project_manager
    if project_manager.current_project:
        proj = project_manager.get_project(project_manager.current_project)
        if proj:
            return proj.workspace / path
    return Path.cwd() / path


def _get_project_root() -> Path:
    from butler.core.project_manager import project_manager
    if project_manager.current_project:
        proj = project_manager.get_project(project_manager.current_project)
        if proj:
            return proj.workspace
    return Path.cwd()
