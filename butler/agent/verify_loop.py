from __future__ import annotations
import asyncio, json, logging, os, re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TEST_COMMANDS = {
    "python": "python -m pytest {test_file} -x -q --tb=short 2>&1 | head -50",
    "javascript": "npx jest {test_file} --no-coverage 2>&1 | head -50",
    "typescript": "npx jest {test_file} --no-coverage 2>&1 | head -50",
}

_TEST_PATTERNS = {
    "python": [
        "tests/test_{stem}.py",
        "tests/{stem}_test.py",
        "test_{stem}.py",
        "{parent}/tests/test_{stem}.py",
        "{parent}/test_{stem}.py",
    ],
    "javascript": [
        "{stem}.test.js",
        "{stem}.spec.js",
        "__tests__/{stem}.test.js",
        "{parent}/__tests__/{stem}.test.js",
    ],
    "typescript": [
        "{stem}.test.ts",
        "{stem}.spec.ts",
        "__tests__/{stem}.test.ts",
        "{parent}/__tests__/{stem}.test.ts",
    ],
}

def detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    mapping = {".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript"}
    return mapping.get(ext, "")

def find_test_file(source_path: str, project_root: str = "") -> Optional[str]:
    """Find the test file corresponding to a source file."""
    p = Path(source_path)
    stem = p.stem
    parent = str(p.parent)
    lang = detect_language(source_path)
    if not lang:
        return None

    root = Path(project_root) if project_root else p.parent
    patterns = _TEST_PATTERNS.get(lang, [])

    for pattern in patterns:
        candidate = pattern.format(stem=stem, parent=parent)
        full = root / candidate
        if full.exists():
            return str(full)
        # Also try from source parent
        full2 = p.parent / candidate
        if full2.exists():
            return str(full2)
    return None

async def run_verification(
    edited_file: str,
    project_root: str = "",
    timeout: int = 30,
) -> dict:
    """Run tests for an edited file. Returns {verified, test_file, output, error}."""
    test_file = find_test_file(edited_file, project_root)
    if not test_file:
        return {"verified": None, "test_file": None, "output": "未找到对应的测试文件", "skipped": True}

    lang = detect_language(edited_file)
    cmd_template = _TEST_COMMANDS.get(lang)
    if not cmd_template:
        return {"verified": None, "test_file": test_file, "output": f"不支持的语言: {lang}", "skipped": True}

    cmd = cmd_template.format(test_file=test_file)
    cwd = project_root or str(Path(edited_file).parent)

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace")
        err_output = stderr.decode("utf-8", errors="replace")
        combined = (output + "\n" + err_output).strip()

        return {
            "verified": proc.returncode == 0,
            "test_file": test_file,
            "exit_code": proc.returncode,
            "output": combined[:2000],
        }
    except asyncio.TimeoutError:
        return {"verified": False, "test_file": test_file, "output": f"测试超时（{timeout}秒）", "error": "timeout"}
    except Exception as e:
        return {"verified": None, "test_file": test_file, "output": str(e), "error": str(e)}

def format_verification_result(result: dict) -> str:
    """Format verification result as text to append to tool output."""
    if result.get("skipped"):
        return ""

    test_file = result.get("test_file", "?")
    if result.get("verified"):
        return f"\n\n[自动验证通过] 测试文件: {test_file}"
    elif result.get("verified") is False:
        output = result.get("output", "")[:800]
        return (
            f"\n\n[自动验证失败] 测试文件: {test_file}\n"
            f"测试输出:\n{output}\n"
            f"请检查修改是否引入了问题。"
        )
    return ""
