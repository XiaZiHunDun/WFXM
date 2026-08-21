#!/usr/bin/env python3
"""Idempotent patch: add Butler v5 vitest mapping to post_tool_use_hook.py."""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "# === Butler v5 PostToolUse (auto) ==="

SNIPPET = '''
# === Butler v5 PostToolUse (auto) ===
V5_FILE_TO_TESTS: list[tuple[str, list[str], str]] = [
    (
        r"^butler-v5/apps/api/src/wechat-inbound-butler\\.ts$",
        ["apps/api/src/wechat-inbound-butler.test.ts"],
        "v5 butler loop",
    ),
    (
        r"^butler-v5/apps/api/src/tool-boundary\\.ts$",
        ["apps/api/src/tool-boundary.test.ts"],
        "v5 tool boundary",
    ),
    (
        r"^butler-v5/apps/api/src/workspace-tools\\.ts$",
        ["apps/api/src/workspace-tools.test.ts"],
        "v5 workspace tools",
    ),
    (
        r"^butler-v5/packages/runtime/src/(agent-kernel|run-engine|capability-boundary)\\.ts$",
        [
            "packages/runtime/src/run-engine.test.ts",
            "packages/runtime/src/capability-boundary.test.ts",
        ],
        "v5 runtime core",
    ),
    (
        r"^butler-v5/packages/persistence/src/migrations/",
        ["packages/persistence/src/runtime-schema.test.ts"],
        "v5 persistence schema",
    ),
    (
        r"^butler-v5/apps/api/src/mcp-",
        [
            "apps/api/src/mcp-bootstrap.test.ts",
            "apps/api/src/mcp-config.test.ts",
        ],
        "v5 MCP bootstrap",
    ),
]

V5_TEST_TIMEOUT = 120


def _find_matching_v5_tests(file_path_str: str) -> tuple[list[str], str]:
    if not file_path_str:
        return [], ""
    try:
        rel_str = Path(file_path_str).resolve().relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return [], ""
    import re

    for pattern, tests, desc in V5_FILE_TO_TESTS:
        if re.match(pattern, rel_str):
            return tests, desc
    return [], ""


def _run_v5_vitest(test_files: list[str], desc: str) -> int:
    import os
    import subprocess

    if not test_files:
        return 0
    butler_v5 = REPO_ROOT / "butler-v5"
    if not butler_v5.is_dir():
        return 0
    print(f"[AI Guard] 修改检测：正在运行 v5 {desc}...", file=sys.stderr)
    cmd = ["pnpm", "exec", "vitest", "run", *test_files, "--reporter=dot"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(butler_v5),
            capture_output=True,
            text=True,
            timeout=V5_TEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[AI Guard] WARNING: v5 {desc} 超时（>{V5_TEST_TIMEOUT}s）",
            file=sys.stderr,
        )
        return 0
    except FileNotFoundError:
        return 0

    if result.returncode == 0:
        print(f"[AI Guard] ✅ v5 {desc} 通过", file=sys.stderr)
        return 0

    print(f"[AI Guard] ❌ v5 {desc} 失败！", file=sys.stderr)
    for line in (result.stdout + result.stderr).splitlines():
        if "FAIL" in line or "Error" in line or "failed" in line.lower():
            print(f"  {line}", file=sys.stderr)
    print(
        f"\\n[AI Guard] 请手动：cd butler-v5 && pnpm exec vitest run {' '.join(test_files)}",
        file=sys.stderr,
    )
    return 0
'''

MAIN_PATCH_OLD = """    tests, desc = _find_matching_tests(file_path)
    if not tests:
        return 0

    return _run_quick_tests(tests, desc)"""

MAIN_PATCH_NEW = """    v5_tests, v5_desc = _find_matching_v5_tests(file_path)
    if v5_tests:
        return _run_v5_vitest(v5_tests, v5_desc)

    tests, desc = _find_matching_tests(file_path)
    if not tests:
        return 0

    return _run_quick_tests(tests, desc)"""


def main() -> int:
    global REPO_ROOT
    repo = Path(__file__).resolve().parent.parent.parent
    REPO_ROOT = repo
    target = repo / "scripts" / "ai_guard" / "post_tool_use_hook.py"
    if not target.is_file():
        print(f"ERROR: missing {target}", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print("SKIP: post_tool_use_hook.py already has v5 block")
        return 0

    anchor = "# 快速测试超时（秒）\nQUICK_TEST_TIMEOUT = 30"
    if anchor not in text:
        print("ERROR: anchor not found in post_tool_use_hook.py", file=sys.stderr)
        return 1

    text = text.replace(anchor, anchor + "\n" + SNIPPET.strip() + "\n")

    if MAIN_PATCH_OLD not in text:
        print("ERROR: main() patch anchor not found", file=sys.stderr)
        return 1
    text = text.replace(MAIN_PATCH_OLD, MAIN_PATCH_NEW)

    target.write_text(text, encoding="utf-8")
    print("OK: patched post_tool_use_hook.py with v5 vitest mapping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
