#!/usr/bin/env python3
"""Validate workflow_state.json against on-disk review reports (novel-factory)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_DIR = ROOT / "06_意见仓库" / "04_正文_审核"
STATE_FILE = ROOT / "workflow_state.json"

_P0_CLEAR = re.compile(
    r"(无\s*P0|P0\s*问题[：:]\s*无|###\s*P0问题[：:]\s*无|无P0问题)",
    re.IGNORECASE,
)
_P0_FAIL = re.compile(
    r"(不通过.*P0|存在\s*\d+\s*个\s*P0|P0\s*优先|工具性存在.*P0)",
    re.IGNORECASE,
)
_OPEN_FIX = re.compile(r"(待修复|需修改)", re.IGNORECASE)
_FIXED = re.compile(r"(已修复|全部修复|修复完成)", re.IGNORECASE)


def audit_open_issues(text: str) -> list[str]:
    """Heuristic: flag reports that likely still have unresolved P0/fix work."""
    issues: list[str] = []
    if _P0_FAIL.search(text) and not _P0_CLEAR.search(text):
        issues.append("审核结论含未闭合 P0")
    if _OPEN_FIX.search(text) and not _FIXED.search(text):
        issues.append("含待修复/需修改且无已修复标记")
    return issues


def validate_completed_batches(state: dict) -> list[str]:
    errors: list[str] = []
    completed = (state.get("review_queue") or {}).get("completed") or []
    if not isinstance(completed, list):
        return ["review_queue.completed 格式异常"]

    audit_stems = {p.stem for p in REVIEW_DIR.glob("*_审核.md")}
    for entry in completed:
        if not isinstance(entry, dict):
            continue
        batch_id = str(entry.get("batch_id") or "").strip()
        result = str(entry.get("result") or "").strip()
        if result and ("待修复" in result or "未通过" in result):
            errors.append(f"completed 批次 {batch_id} result 仍为未闭合: {result}")
        chapters = entry.get("chapters") or []
        if chapters and batch_id.startswith("reviewer"):
            first, last = str(chapters[0]), str(chapters[-1])
            needle = f"{first}-{last}".replace("ch", "ch")
            if not any(needle in s or batch_id in s for s in audit_stems):
                errors.append(f"completed 批次 {batch_id} 未找到对应审核报告（期望含 {first}…{last}）")
    return errors


def scan_audit_reports() -> list[str]:
    warnings: list[str] = []
    for path in sorted(REVIEW_DIR.glob("*_审核.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for msg in audit_open_issues(text):
            warnings.append(f"{path.name}: {msg}")
    return warnings


def main() -> int:
    if not STATE_FILE.is_file():
        print(f"缺少 {STATE_FILE}", file=sys.stderr)
        return 1

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    report_count = len(list(REVIEW_DIR.glob("*_审核.md")))

    print(f"审核报告数量: {report_count}")
    print(f"workflow: {state.get('current_phase')} / {state.get('current_step')}")

    errors = validate_completed_batches(state)
    warnings = scan_audit_reports()

    if errors:
        print("错误:")
        for e in errors:
            print(f"  - {e}")

    if warnings:
        print("警告（可能仍有未闭合问题，请人工核对）:")
        for w in warnings[:20]:
            print(f"  - {w}")
        if len(warnings) > 20:
            print(f"  … 另有 {len(warnings) - 20} 条")
        if state.get("current_phase") == "PHASE_COMPLETE":
            print(
                "(当前 PHASE_COMPLETE：多为历史审核记录中的「需修改」行，"
                "不代表发布阻断)"
            )

    if errors:
        return 1
    if warnings:
        print("进度验证: 通过（有警告）")
        return 0
    print("进度验证: 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
