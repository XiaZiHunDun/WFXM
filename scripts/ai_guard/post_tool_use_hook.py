#!/usr/bin/env python3
"""PostToolUse hook: 文件修改后自动运行相关测试，快速发现回归。

读取 stdin JSON（Claude Code hook 格式），根据修改的文件路径
选择对应的测试子集运行。如果测试失败，输出警告（不阻止已完成的操作）。

使用方式（.claude/settings.json）:
    "PostToolUse": [{"command": "python3 scripts/ai_guard/post_tool_use_hook.py"}]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# === 文件路径 → 测试映射 ===
# 修改某个文件后，自动运行对应的测试子集。
# 测试子集选择原则：快速（<30秒）、覆盖核心功能、不依赖外部服务。

FILE_TO_TESTS: list[tuple[str, list[str], str]] = [
    # 核心循环
    (
        r"^butler/core/agent_loop/",
        ["tests/test_butler_v4.py::TestE2EToolFlow", "tests/test_cc_p3_p4_features.py"],
        "核心循环测试",
    ),
    (
        r"^butler/core/tool_batch",
        ["tests/test_tool_batch.py", "tests/test_tool_result_storage.py"],
        "工具批次测试",
    ),
    (
        r"^butler/core/llm_retry",
        ["tests/test_retry_policy.py"],
        "LLM 重试测试",
    ),
    (
        r"^butler/core/llm/",
        ["tests/test_retry_policy.py"],
        "LLM 重试测试",
    ),
    # 网关
    (
        r"^butler/gateway/",
        ["tests/gateway/test_gateway_handler.py"],
        "网关处理器测试",
    ),
    (
        r"^butler/gateway/locked_phases",
        ["tests/gateway/test_gateway_handler.py", "tests/test_cc_p3_p4_features.py"],
        "网关阶段测试",
    ),
    # 记忆
    (
        r"^butler/memory/",
        ["tests/test_memory_p1_p2.py"],
        "记忆模块测试",
    ),
    (
        r"^butler/memory/project_memory",
        ["tests/test_memory_p1_p2.py"],
        "项目记忆测试",
    ),
    # 技能
    (
        r"^butler/skills/",
        ["tests/test_skill_registry_p2.py"],
        "技能管理测试",
    ),
    (
        r"^butler/skills/manager",
        ["tests/test_skill_registry_p2.py", "tests/test_r2_8_skill_load_error.py"],
        "技能管理器测试",
    ),
    # 开发引擎
    (
        r"^butler/dev_engine/",
        ["tests/test_swebench_entry_gate.py"],
        "开发引擎测试",
    ),
    # 契约层
    (
        r"^butler/contracts/",
        ["tests/contracts/"],
        "契约层测试",
    ),
    # 权限
    (
        r"^butler/permissions/",
        ["tests/test_r2_11_permissions_fail_closed.py", "tests/test_p2_workflow_permissions.py"],
        "权限模块测试",
    ),
    # 配置
    (
        r"^butler/configuration/",
        ["tests/test_butler_config.py", "tests/test_env_parse_r8.py"],
        "配置模块测试",
    ),
    # 传输层
    (
        r"^butler/transport/",
        ["tests/test_transport_providers.py"],
        "传输层测试",
    ),
    # === G5: 补全测试映射 ===
    # 编排
    (
        r"^butler/orchestrator/",
        ["tests/test_orchestrator.py", "tests/test_butler_orchestrator.py"],
        "编排器测试",
    ),
    # 委派
    (
        r"^butler/delegate/",
        ["tests/test_delegate_init.py", "tests/test_async_delegate.py"],
        "委派模块测试",
    ),
    # 工作流
    (
        r"^butler/workflows/",
        ["tests/test_workflows.py", "tests/test_workflow_runner.py"],
        "工作流测试",
    ),
    # MCP
    (
        r"^butler/mcp/",
        ["tests/test_mcp_features.py", "tests/test_mcp_catalog.py"],
        "MCP 模块测试",
    ),
    # 韧性（resilience）
    (
        r"^butler/resilience/",
        ["tests/gateway/test_message_queue.py"],
        "韧性模块测试",
    ),
    # 钩子
    (
        r"^butler/hooks/",
        ["tests/test_cc_p3_p4_features.py"],
        "钩子模块测试",
    ),
    # 黑板（blackboard）
    (
        r"^butler/blackboard/",
        ["tests/contracts/"],
        "黑板模块测试",
    ),
]

# 快速测试超时（秒）
QUICK_TEST_TIMEOUT = 30


def _read_stdin_json() -> dict[str, Any]:
    """读取 Claude Code hook 的 stdin JSON 输入。"""
    try:
        raw = sys.stdin.read()
        if raw.strip():
            return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _extract_file_path(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """从工具调用中提取目标文件路径。"""
    if tool_name in ("Edit", "Write", "DeleteFile"):
        return tool_input.get("file_path")
    return None


def _find_matching_tests(file_path_str: str) -> tuple[list[str], str]:
    """根据文件路径找到对应的测试子集。"""
    if not file_path_str:
        return [], ""

    try:
        abs_path = Path(file_path_str).resolve()
        rel = abs_path.relative_to(REPO_ROOT)
        rel_str = rel.as_posix()
    except (ValueError, OSError):
        return [], ""

    for pattern, tests, desc in FILE_TO_TESTS:
        import re
        if re.match(pattern, rel_str):
            return tests, desc

    return [], ""


def _run_quick_tests(tests: list[str], desc: str) -> int:
    """运行快速测试子集，返回退出码。"""
    if not tests:
        return 0

    print(f"[AI Guard] 修改检测：正在运行 {desc}...", file=sys.stderr)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    cmd = ["python", "-m", "pytest"] + tests + ["-q", "--tb=line", "--no-header", "-x"]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=QUICK_TEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[AI Guard] WARNING: {desc} 运行超时（>{QUICK_TEST_TIMEOUT}s），"
            f"请手动运行验证：\n  python -m pytest {' '.join(tests)} -q",
            file=sys.stderr,
        )
        return 0
    except FileNotFoundError:
        # pytest 不在 PATH 中，尝试其他路径
        return 0

    if result.returncode == 0:
        print(f"[AI Guard] ✅ {desc} 通过", file=sys.stderr)
        return 0

    # 测试失败，输出摘要
    print(f"[AI Guard] ❌ {desc} 失败！", file=sys.stderr)
    print(f"[AI Guard] 失败的测试：", file=sys.stderr)

    # 提取失败的测试行
    for line in result.stdout.splitlines():
        if line.startswith("FAILED") or line.startswith("ERROR"):
            print(f"  {line}", file=sys.stderr)

    print(
        f"\n[AI Guard] 请修复失败的测试，或手动运行完整测试验证：\n"
        f"  python -m pytest {' '.join(tests)} -v",
        file=sys.stderr,
    )
    return 0  # 不阻止已完成的操作


def main() -> int:
    hook_input = _read_stdin_json()

    if hook_input:
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})
        file_path = _extract_file_path(tool_name, tool_input) or ""
    elif len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        return 0

    if not file_path:
        return 0

    tests, desc = _find_matching_tests(file_path)
    if not tests:
        return 0

    return _run_quick_tests(tests, desc)


if __name__ == "__main__":
    sys.exit(main())
