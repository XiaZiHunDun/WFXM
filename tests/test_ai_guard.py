"""F4: AI guard 脚本自身的回归测试。

验证 PreToolUse/PostToolUse/file_size_check 三个脚本的核心行为：
- 受保护文件检测
- 危险模式检测
- DeleteFile file_paths（数组）处理
- MultiEdit edits 处理
- 文件大小阈值

这些测试确保 AI 工具修改 ai_guard 脚本时不会引入回归。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AI_GUARD_DIR = REPO_ROOT / "scripts" / "ai_guard"
PRE_TOOL_USE_HOOK = AI_GUARD_DIR / "pre_tool_use_hook.py"
POST_TOOL_USE_HOOK = AI_GUARD_DIR / "post_tool_use_hook.py"
FILE_SIZE_CHECK = AI_GUARD_DIR / "file_size_check.py"


def _run_pre_tool_use(hook_input: dict) -> tuple[int, str, str]:
    """运行 pre_tool_use_hook 并返回 (exit_code, stdout, stderr)。

    注意：Claude Code hook 协议通过 stdout JSON 的 decision 字段控制行为，
    而非 exit code。block 操作返回 exit code 0 + JSON {"decision": "block"}。
    """
    proc = subprocess.run(
        [sys.executable, str(PRE_TOOL_USE_HOOK)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _is_blocked(stdout: str) -> bool:
    """检查 stdout 是否包含 block decision。"""
    try:
        # stdout 可能有多行，找 JSON 行
        for line in stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                return data.get("decision") == "block"
    except json.JSONDecodeError:
        pass
    return False


# === PreToolUse: 受保护文件检测 ===

@pytest.mark.parametrize("protected_file", [
    "butler/core/agent_loop/loop.py",
    "butler/contracts/__init__.py",
    "pyproject.toml",
    ".claude/settings.json",
])
def test_protected_file_edit_blocked(protected_file: str):
    """Edit 受保护文件应被阻止。"""
    rc, out, err = _run_pre_tool_use({
        "tool_name": "Edit",
        "tool_input": {"file_path": str(REPO_ROOT / protected_file)},
    })
    assert _is_blocked(out), f"{protected_file} should be blocked"


def test_protected_file_write_blocked():
    """Write 受保护文件应被阻止。"""
    rc, out, err = _run_pre_tool_use({
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(REPO_ROOT / "butler" / "core" / "agent_loop" / "loop.py"),
            "content": "# malicious",
        },
    })
    assert _is_blocked(out)


# === F1: DeleteFile file_paths（数组）处理 ===

def test_delete_file_with_array_blocks_protected():
    """F1: DeleteFile 使用 file_paths 数组时应检测受保护文件。"""
    rc, out, err = _run_pre_tool_use({
        "tool_name": "DeleteFile",
        "tool_input": {
            "file_paths": [
                str(REPO_ROOT / "butler" / "contracts" / "__init__.py"),
                str(REPO_ROOT / "butler" / "utilities" / "env_parse.py"),
            ]
        },
    })
    assert _is_blocked(out), "DeleteFile with protected file_paths should be blocked"


def test_delete_file_with_array_allows_non_protected(tmp_path):
    """F1: DeleteFile 非受保护文件应通过。"""
    safe_file = tmp_path / "safe.py"
    safe_file.write_text("# safe")
    rc, out, err = _run_pre_tool_use({
        "tool_name": "DeleteFile",
        "tool_input": {"file_paths": [str(safe_file)]},
    })
    assert not _is_blocked(out)


# === F2: MultiEdit 处理 ===

def test_multiedit_with_wildcard_import_blocked():
    """F2: MultiEdit 含通配符 import 应被阻止。"""
    rc, out, err = _run_pre_tool_use({
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(REPO_ROOT / "butler" / "test_multiedit.py"),
            "edits": [
                {"old_string": "a", "new_string": "from os import *\n"},
                {"old_string": "b", "new_string": "normal code\n"},
            ],
        },
    })
    assert _is_blocked(out), "MultiEdit with wildcard import should be blocked"


def test_multiedit_normal_edits_allowed(tmp_path):
    """F2: MultiEdit 正常编辑应通过。"""
    safe_file = tmp_path / "safe.py"
    safe_file.write_text("a\nb\n")
    rc, out, err = _run_pre_tool_use({
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": str(safe_file),
            "edits": [
                {"old_string": "a", "new_string": "x"},
                {"old_string": "b", "new_string": "y"},
            ],
        },
    })
    assert not _is_blocked(out)


# === G4: 危险模式检测 ===

def test_write_with_wildcard_import_blocked():
    """G4: Write 含通配符 import 应被阻止。"""
    rc, out, err = _run_pre_tool_use({
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(REPO_ROOT / "butler" / "test_wildcard.py"),
            "content": "from os.path import *\n\ndef foo(): pass\n",
        },
    })
    assert _is_blocked(out)


def test_edit_with_wildcard_import_blocked():
    """G4: Edit 含通配符 import 应被阻止。"""
    rc, out, err = _run_pre_tool_use({
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(REPO_ROOT / "butler" / "test_edit.py"),
            "old_string": "old",
            "new_string": "from os import *\n",
        },
    })
    assert _is_blocked(out)


def test_normal_edit_allowed():
    """正常 Edit 非受保护文件应通过。"""
    rc, out, err = _run_pre_tool_use({
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(REPO_ROOT / "butler" / "utilities" / "env_parse.py"),
            "old_string": "a",
            "new_string": "b",
        },
    })
    assert not _is_blocked(out)


# === 文件大小守卫 ===

def test_file_size_check_ci_mode():
    """G6: file_size_check --ci 模式应能运行并退出 0 或 1（不崩溃）。"""
    proc = subprocess.run(
        [sys.executable, str(FILE_SIZE_CHECK), "--ci"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    # 0 = 全部通过，1 = 有文件 >1200 行
    assert proc.returncode in (0, 1), f"Unexpected exit code: {proc.returncode}"


def test_file_size_check_specific_file(tmp_path):
    """G6: file_size_check 指定小文件应通过。"""
    small_file = tmp_path / "small.py"
    small_file.write_text("# small file\n")
    proc = subprocess.run(
        [sys.executable, str(FILE_SIZE_CHECK), str(small_file)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0


# === PostToolUse hook 可导入性 ===

def test_post_tool_use_hook_importable():
    """PostToolUse hook 应可被 Python 导入（无语法错误）。"""
    sys.path.insert(0, str(AI_GUARD_DIR))
    try:
        import importlib
        mod = importlib.import_module("post_tool_use_hook")
        assert hasattr(mod, "FILE_TO_TESTS")
        assert len(mod.FILE_TO_TESTS) >= 20, "FILE_TO_TESTS should have at least 20 entries"
    finally:
        sys.path.pop(0)


def test_post_tool_use_covers_core_agent_loop():
    """PostToolUse 应覆盖 butler/core/agent_loop/。"""
    sys.path.insert(0, str(AI_GUARD_DIR))
    try:
        import importlib
        mod = importlib.import_module("post_tool_use_hook")
        patterns = [p[0] for p in mod.FILE_TO_TESTS]
        assert any("agent_loop" in p for p in patterns), "agent_loop not covered"
    finally:
        sys.path.pop(0)
