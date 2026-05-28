#!/usr/bin/env bash
# Repository cleanup audit: structure drift, large files, git hygiene.
set -euo pipefail

cd "$(dirname "$0")/.."

REPORT_DIR="${REPORT_DIR:-logs/maintenance}"
mkdir -p "${REPORT_DIR}"
TS="$(date +%Y%m%d-%H%M%S)"
OUT_MD="${REPORT_DIR}/repo-cleanup-${TS}.md"

python3 - <<'PY' >"${OUT_MD}"
from __future__ import annotations

import os
import subprocess
from pathlib import Path

repo = Path(".").resolve()
allowed_root = {
    ".cursor",
    ".github",
    ".git",
    ".gitignore",
    ".env.example",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "README.md",
    "STRUCTURE.md",
    "archive",
    "butler",
    "butler_system.egg-info",
    "docs",
    "logs",
    "projects",
    "pyproject.toml",
    "reference",
    "requirements.lock",
    "scripts",
    "tests",
    "__pycache__",
    "MagicMock",
}

local_runtime_entries = {
    ".butler",
    ".env",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

root_entries = sorted(p.name for p in repo.iterdir())
unexpected = [
    name for name in root_entries
    if name not in allowed_root and name not in local_runtime_entries
]
local_runtime_found = [name for name in root_entries if name in local_runtime_entries]

def run(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return (res.stdout or res.stderr).strip()
    except Exception as exc:  # noqa: BLE001
        return f"<error: {exc}>"

status_short = run(["git", "status", "--short"])
tracked_files_raw = run(["git", "ls-files"])
tracked_files = [line for line in tracked_files_raw.splitlines() if line.strip()]

large_files: list[tuple[str, int]] = []
for rel in tracked_files:
    path = repo / rel
    if path.is_file():
        size = path.stat().st_size
        if size >= 5 * 1024 * 1024:
            large_files.append((rel, size))
large_files.sort(key=lambda x: x[1], reverse=True)

print("# 仓库清理审计报告")
print()
print(f"- 根目录: `{repo}`")
print(f"- Root 条目数: {len(root_entries)}")
print(f"- Git tracked 文件数: {len(tracked_files)}")
print()

print("## 1) 根目录结构漂移检查")
if unexpected:
    print()
    print("发现未纳入白名单的 root 条目：")
    for name in unexpected:
        print(f"- `{name}`")
else:
    print()
    print("未发现 root 结构漂移。")

print()
print("## 1.1) 本地运行态条目（可接受）")
if local_runtime_found:
    print()
    for name in local_runtime_found:
        print(f"- `{name}`")
else:
    print()
    print("未发现本地运行态条目。")

print()
print("## 2) 大文件检查（tracked >= 5MB）")
if large_files:
    print()
    for rel, size in large_files[:30]:
        mb = size / (1024 * 1024)
        print(f"- `{rel}`: {mb:.2f} MB")
else:
    print()
    print("未发现 >= 5MB 的 tracked 文件。")

print()
print("## 3) 工作区变更概览")
print()
if status_short:
    print("```text")
    print(status_short)
    print("```")
else:
    print("工作区干净。")

print()
print("## 4) 清理建议")
print()
print("- 保持 root 目录最小化，临时文件统一放入 `logs/maintenance/`。")
print("- 超过 5MB 的产物默认不入库，改为归档路径或 release 附件。")
print("- 开发中产生的中间输出优先写入 `projects/*/.butler/` 或 `logs/`。")
print("- 发版前固定执行：`bash scripts/project-health-check.sh quick`。")
PY

echo "repo cleanup report: ${OUT_MD}"
