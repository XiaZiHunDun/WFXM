#!/usr/bin/env python3
"""PreToolUse hook: 阻止 AI 工具修改关键受保护文件。

读取 stdin JSON（Claude Code hook 格式），检查目标文件是否在受保护清单中。
如果受保护，返回 block 决策并给出原因。

使用方式（.claude/settings.json）:
    "PreToolUse": [{"command": "python3 scripts/ai_guard/pre_tool_use_hook.py"}]

也支持直接命令行调用:
    python3 scripts/ai_guard/pre_tool_use_hook.py <file_path>
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# === 受保护文件清单 ===
# 这些文件是项目的核心骨架，AI 工具不应该直接修改。
# 如果需要修改，必须先运行完整门禁并通过人工审查。

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 完全禁止修改的文件（AI 工具绝不能动）
PROTECTED_FILES: set[str] = {
    # 核心循环 - 项目的心脏
    "butler/core/agent_loop/loop.py",
    # 契约层 - 接口定义，改动会破坏所有实现
    "butler/contracts/__init__.py",
    # 配置入口
    "pyproject.toml",
    # AI 工具配置（防止 AI 自我解除保护）
    ".claude/settings.json",
    "scripts/ai_guard/pre_tool_use_hook.py",
    "scripts/ai_guard/post_tool_use_hook.py",
    # 黑板交接机制
    ".blackboard/README.md",
    # === Butler v5 protected (auto) ===
    "butler-v5/packages/persistence/src/migrations/0001_initial.sql",
    "butler-v5/apps/api/src/wechat-inbound-butler.ts",
    "butler-v5/packages/runtime/src/agent-kernel.ts",
    "butler-v5/packages/runtime/src/run-engine.ts",
    "butler-v5/packages/runtime/src/bridge.ts",
    "butler-v5/packages/runtime/src/capability-boundary.ts",
    "butler-v5/apps/api/src/tool-boundary.ts",
    "butler-v5/apps/api/src/capability-guard.ts",
    "butler-v5/apps/api/src/workspace-tools.ts",
}

# 受保护目录前缀（修改需要额外警告）
PROTECTED_DIR_PATTERNS: list[tuple[str, str]] = [
    # 契约 Port 接口 - 改动会破坏所有实现
    (r"^butler/contracts/", "契约层 Port 接口"),
    # 层依赖规则 - 改动会绕过层依赖检查
    (r"^tests/layer_import_rules", "层依赖规则"),
    # 门禁脚本 - 改动会绕过门禁检查
    (r"^scripts/.*_gate\.sh$", "门禁脚本"),
    (r"^scripts/ai_guard/", "AI 保护脚本"),
    # Blackboard 交接
    (r"^\.blackboard/", "黑板交接机制"),
    # === Butler v5 protected (auto) ===
    (r"^butler-v5/packages/persistence/src/migrations/", "v5 生产 schema"),
]

# Shim 文件模式 - 警告但不阻止
SHIM_PATTERN = re.compile(
    r'^""".*?Deprecated:.*?package instead\.',
    re.DOTALL,
)


def _read_stdin_json() -> dict[str, Any]:
    """读取 Claude Code hook 的 stdin JSON 输入。"""
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _extract_file_paths(tool_name: str, tool_input: dict[str, Any]) -> list[str]:
    """从工具调用中提取目标文件路径列表。

    支持的工具：
    - Edit: file_path (单个)
    - Write: file_path (单个)
    - MultiEdit: file_path (单个，但含多个 edit)
    - DeleteFile: file_paths (数组，复数)
    """
    paths: list[str] = []

    if tool_name in ("Edit", "Write", "MultiEdit"):
        path = tool_input.get("file_path")
        if isinstance(path, str):
            paths.append(path)
    elif tool_name == "DeleteFile":
        # DeleteFile 使用 file_paths（复数，数组）
        file_paths = tool_input.get("file_paths")
        if isinstance(file_paths, list):
            paths.extend(p for p in file_paths if isinstance(p, str))
        # 兼容：有些客户端可能用 file_path（单数）
        single = tool_input.get("file_path")
        if isinstance(single, str):
            paths.append(single)

    return paths


# === G4: 危险模式检测 ===

# 危险模式正则
import re as _re

DANGEROUS_PATTERNS: list[tuple[_re.Pattern[str], str, str]] = [
    # 通配符 import — 污染命名空间，隐藏依赖
    (
        _re.compile(r"^\s*from\s+\S+\s+import\s+\*", _re.MULTILINE),
        "block",
        "通配符 import (from X import *) 污染命名空间，请显式列出导入名。",
    ),
    # 删除 __all__ — 破坏模块公共接口契约
    (
        _re.compile(r"^\s*#\s*__all__\s*=|^\s*del\s+__all__", _re.MULTILINE),
        "warn",
        "检测到注释或删除 __all__ — 这会破坏模块的公共接口契约。",
    ),
]


def _check_dangerous_patterns(
    tool_name: str,
    tool_input: dict[str, Any],
    file_path_str: str,
) -> tuple[str, str]:
    """检查 Edit/Write/MultiEdit 的内容是否包含危险模式。

    返回 (severity, reason)。
    severity: "block" / "warn" / "ok"
    """
    if not file_path_str or not file_path_str.endswith(".py"):
        return "ok", ""

    # Write 操作：检查整个新内容
    if tool_name == "Write":
        content = tool_input.get("content", "")
        if not isinstance(content, str):
            return "ok", ""
        return _scan_content_for_patterns(content, file_path_str)

    # Edit 操作：检查 new_string
    if tool_name == "Edit":
        new_string = tool_input.get("new_string", "")
        if not isinstance(new_string, str):
            return "ok", ""
        return _scan_content_for_patterns(new_string, file_path_str)

    # MultiEdit 操作：检查所有 edits 的 new_string
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        if not isinstance(edits, list):
            return "ok", ""
        reasons: list[str] = []
        worst_severity = "ok"
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                continue
            new_string = edit.get("new_string", "")
            if not isinstance(new_string, str):
                continue
            sev, reason = _scan_content_for_patterns(new_string, file_path_str)
            if sev == "block":
                worst_severity = "block"
                reasons.append(f"edit[{i}]: {reason}")
            elif sev == "warn" and worst_severity != "block":
                worst_severity = "warn"
                reasons.append(f"edit[{i}]: {reason}")
        if reasons:
            return worst_severity, "\n".join(reasons)
        return "ok", ""

    return "ok", ""


def _scan_content_for_patterns(content: str, file_path_str: str) -> tuple[str, str]:
    """扫描内容中的危险模式。"""
    reasons: list[str] = []
    worst_severity = "ok"

    for pattern, severity, reason in DANGEROUS_PATTERNS:
        if pattern.search(content):
            reasons.append(reason)
            if severity == "block":
                worst_severity = "block"
            elif severity == "warn" and worst_severity != "block":
                worst_severity = "warn"

    if reasons:
        rel = ""
        try:
            rel = str(Path(file_path_str).resolve().relative_to(REPO_ROOT).as_posix())
        except (ValueError, OSError):
            rel = file_path_str
        combined = f"文件 {rel} 包含危险模式：\n  - " + "\n  - ".join(reasons)
        return worst_severity, combined

    return "ok", ""


def _check_protected(file_path_str: str) -> tuple[bool, str, str]:
    """检查文件是否受保护。

    返回 (is_protected, severity, reason)。
    severity: "block"（阻止）, "warn"（警告）, "ok"（允许）。
    """
    if not file_path_str:
        return False, "ok", ""

    # 转为相对路径
    try:
        abs_path = Path(file_path_str).resolve()
        rel = abs_path.relative_to(REPO_ROOT)
        rel_str = rel.as_posix()
    except (ValueError, OSError):
        return False, "ok", ""

    # 检查完全禁止修改的文件
    if rel_str in PROTECTED_FILES:
        return True, "block", (
            f"文件 {rel_str} 是核心受保护文件，禁止 AI 工具直接修改。"
            f"如需修改，请先在 GitHub 创建 issue 说明原因，"
            f"由人工修改并运行完整门禁。"
        )

    # 检查受保护目录前缀
    for pattern, desc in PROTECTED_DIR_PATTERNS:
        if re.match(pattern, rel_str):
            # 检查是否是 shim 文件
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
                if SHIM_PATTERN.match(content):
                    return True, "warn", (
                        f"文件 {rel_str} 是 shim 文件（向后兼容层）。"
                        f"修改 shim 文件不会影响实际实现。"
                        f"如需修改功能，请修改 {desc} 对应的包目录下的实际实现文件。"
                    )
            except (OSError, UnicodeDecodeError):
                pass

            return True, "warn", (
                f"文件 {rel_str} 属于受保护区域（{desc}）。"
                f"修改前请确认已运行相关门禁：\n"
                f"  - bash scripts/butler-pytest-fast-gate.sh\n"
                f"  - bash scripts/butler-layer-import-gate.sh"
            )

    return False, "ok", ""


def _emit_result(severity: str, reason: str, file_path: str) -> int:
    """输出 hook 结果并返回退出码。"""
    if severity == "block":
        # Claude Code hook 格式：输出 JSON 到 stdout
        result = {
            "decision": "block",
            "reason": reason,
        }
        print(json.dumps(result, ensure_ascii=False))
        # 同时输出到 stderr 供调试
        print(f"[AI Guard] BLOCKED: {file_path}", file=sys.stderr)
        print(f"[AI Guard] Reason: {reason}", file=sys.stderr)
        return 0  # Claude Code 通过 JSON decision 控制行为
    elif severity == "warn":
        # 警告但不阻止
        result = {
            "decision": "approve",
            "reason": reason,
        }
        print(json.dumps(result, ensure_ascii=False))
        print(f"[AI Guard] WARNING: {file_path}", file=sys.stderr)
        print(f"[AI Guard] {reason}", file=sys.stderr)
        return 0
    else:
        return 0


def main() -> int:
    # CLI 模式优先，避免 TTY 下 stdin.read() 阻塞
    if len(sys.argv) > 1:
        file_paths = [sys.argv[1]]
        tool_name = "Edit"
        tool_input = {}
        hook_input: dict[str, Any] | None = None
    else:
        hook_input = _read_stdin_json()
        if hook_input:
            tool_name = hook_input.get("tool_name", "")
            tool_input = hook_input.get("tool_input", {})
            file_paths = _extract_file_paths(tool_name, tool_input)
        else:
            return 0

    if not file_paths:
        return 0

    # 检查每个文件路径
    for file_path in file_paths:
        # 1. 检查文件路径是否受保护
        is_protected, severity, reason = _check_protected(file_path)

        # 2. 检查内容中的危险模式（G4）
        if hook_input and not is_protected:
            pat_severity, pat_reason = _check_dangerous_patterns(
                tool_name, tool_input, file_path
            )
            if pat_severity == "block":
                severity = "block"
                reason = pat_reason
            elif pat_severity == "warn" and severity != "block":
                severity = "warn"
                reason = pat_reason

        result = _emit_result(severity, reason, file_path)
        if result != 0:
            # 任一文件被阻止，整体阻止
            return result

    # 所有文件都通过
    return 0


if __name__ == "__main__":
    sys.exit(main())
