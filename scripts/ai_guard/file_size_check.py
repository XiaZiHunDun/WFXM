#!/usr/bin/env python3
"""G6: 文件大小守卫。

检查 .py 文件是否超过项目约定的行数上限：
- >800 行：警告（项目约定应拆分）
- >1200 行：阻止（必须拆分才能提交）

使用方式：
    # 检查所有已 stage 的 .py 文件
    python3 scripts/ai_guard/file_size_check.py --staged

    # 检查指定文件
    python3 scripts/ai_guard/file_size_check.py path/to/file.py

    # 检查整个 butler/ 目录（CI 模式）
    python3 scripts/ai_guard/file_size_check.py --ci

退出码：
    0 = 通过（或仅有警告）
    1 = 有文件超过 1200 行（硬限制）
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 项目约定：>800 行警告，>1200 行必须拆分
WARN_LINES = 800
BLOCK_LINES = 1200

# 已知的大文件白名单（历史遗留，不在本次拆分范围）
WHITELIST: set[str] = {
    # 这些是大型 legacy 文件，已被列入待拆分 backlog
}


def _count_lines(file_path: Path) -> int:
    """统计文件行数（包括空行）。"""
    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _get_staged_py_files() -> list[Path]:
    """获取已 stage 的 .py 文件。"""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    files: list[Path] = []
    for line in result.stdout.splitlines():
        if line.endswith(".py"):
            path = REPO_ROOT / line
            if path.exists():
                files.append(path)
    return files


def _get_all_butler_py_files() -> list[Path]:
    """获取 butler/ 下所有 .py 文件（CI 模式）。"""
    return sorted((REPO_ROOT / "butler").rglob("*.py"))


def _check_files(files: list[Path]) -> tuple[list[tuple[Path, int]], list[tuple[Path, int]]]:
    """检查文件列表，返回 (warnings, blocks)。"""
    warnings: list[tuple[Path, int]] = []
    blocks: list[tuple[Path, int]] = []

    for f in files:
        try:
            rel = f.relative_to(REPO_ROOT)
            rel_str = rel.as_posix()
        except ValueError:
            continue

        if rel_str in WHITELIST:
            continue

        line_count = _count_lines(f)
        if line_count > BLOCK_LINES:
            blocks.append((rel, line_count))
        elif line_count > WARN_LINES:
            warnings.append((rel, line_count))

    return warnings, blocks


def main() -> int:
    parser = argparse.ArgumentParser(description="文件大小守卫")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="检查已 stage 的文件")
    group.add_argument("--ci", action="store_true", help="CI 模式：检查整个 butler/ 目录")
    parser.add_argument("files", nargs="*", help="指定文件路径")
    args = parser.parse_args()

    if args.staged:
        files = _get_staged_py_files()
    elif args.ci:
        files = _get_all_butler_py_files()
    elif args.files:
        files = [Path(f).resolve() for f in args.files]
    else:
        parser.print_help()
        return 0

    if not files:
        return 0

    warnings, blocks = _check_files(files)

    if warnings:
        print(f"⚠️  以下文件超过 {WARN_LINES} 行（建议拆分）：", file=sys.stderr)
        for path, n in warnings:
            print(f"   {n:5d} 行  {path}", file=sys.stderr)

    if blocks:
        print(f"❌ 以下文件超过 {BLOCK_LINES} 行（必须拆分）：", file=sys.stderr)
        for path, n in blocks:
            print(f"   {n:5d} 行  {path}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            f"项目约定 .py 文件不超过 {BLOCK_LINES} 行。请将大文件拆分为包：",
            file=sys.stderr,
        )
        print("  1. 创建同名包目录", file=sys.stderr)
        print("  2. 将代码拆分为逻辑子模块", file=sys.stderr)
        print("  3. 原文件改为 shim（保留 __all__ + DeprecationWarning）", file=sys.stderr)
        print("  4. 运行测试验证功能不变", file=sys.stderr)
        return 1

    if not warnings:
        print(f"✅ 文件大小守卫通过（{len(files)} 个文件）", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
