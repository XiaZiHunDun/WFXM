#!/usr/bin/env python3
"""Validate 审核员报告 .md against reviewer_report.schema.json.

用法:
    python validate_reviewer_report.py ch001_审核员A_审核.md [...]

解析流程:
  1. H1 → title
  2. ## 章节信息 (- **k**: v) → chapter_no, reviewer_id
  3. ## 审核详情 (### aspect / - **结论**: ...) → review_aspects 4 字段
  4. ## 审核结论 (**verdict**) → verdict
  5. ## 意见汇总 (markdown 表) → issues[]

退出码: 0 OK / 1 错误 / 2 schema 缺失。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _base import format_cli_errors, run_validator

_ASPECTS = ("逻辑一致性", "人设稳定性", "叙事节奏", "章节连贯性")
_VERDICTS = ("通过", "有条件通过", "不通过")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_KV_RE = re.compile(r"^-\s*\*\*([^*]+)\*\*\s*[:：]\s*(.+?)\s*$", re.MULTILINE)


def _split_sections(text: str) -> dict[str, str]:
    """按 ## 切分；返回 {section_name: body}；H1 留在第一段顶部。"""
    matches = list(_H2_RE.finditer(text))
    sections: dict[str, str] = {}
    if not matches:
        sections["_pre"] = text
        return sections
    if matches[0].start() > 0:
        sections["_pre"] = text[: matches[0].start()]
    for i, m in enumerate(matches):
        name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end]
    return sections


def _h1(text: str) -> str:
    m = _H1_RE.search(text)
    return m.group(1).strip() if m else ""


def _parse_kv_list(section_body: str) -> dict[str, str]:
    """- **k**: v 形式抽取；容忍中文/英文冒号；保留顺序以便查重。"""
    out: dict[str, str] = {}
    for m in _KV_RE.finditer(section_body):
        key = m.group(1).strip()
        val = m.group(2).strip()
        if key not in out:
            out[key] = val
    return out


def _parse_aspects(section_body: str) -> dict[str, str]:
    """### <aspect>\n- **结论**: <verdict>\n  - **说明**: ... 形式抽取 verdict。"""
    out: dict[str, str] = {a: "未填写" for a in _ASPECTS}
    for h3 in _H3_RE.finditer(section_body):
        name = h3.group(1).strip()
        if name not in _ASPECTS:
            continue
        # 在 ### 段尾前找结论
        next_h3 = _H3_RE.search(section_body, h3.end())
        chunk = section_body[h3.end(): next_h3.start() if next_h3 else len(section_body)]
        m = re.search(r"-\s*\*\*结论\*\*\s*[:：]\s*(\S+)", chunk)
        if m:
            out[name] = m.group(1).strip()
    return out


def _parse_verdict(section_body: str) -> str:
    m = re.search(r"\*\*([^*]+)\*\*", section_body)
    return m.group(1).strip() if m else "未填写"


def _parse_issues_table(section_body: str) -> list[dict[str, str]]:
    """markdown 表解析：| priority | type | content |；跳过表头与分隔行。"""
    issues: list[dict[str, str]] = []
    for line in section_body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        # 跳过表头（首行通常是：| 优先级 | 问题类型 | 意见内容 |）
        if any(h in cells[0] for h in ("优先级", "Priority", "---", ":-")):
            continue
        if set(cells[0]) <= {"-", " ", ":"}:
            continue
        priority, issue_type, content = cells[0], cells[1], " ".join(cells[2:])
        issues.append(
            {"priority": priority, "type": issue_type, "content": content}
        )
    return issues


def load_reviewer_report(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")

    title = _h1(text)
    if not title:
        raise ValueError("H1 缺失")

    sections = _split_sections(text)

    info = _parse_kv_list(sections.get("章节信息", ""))
    chapter_no = info.get("章节号", "").strip()
    reviewer_id = info.get("审核员", "").strip()
    if not re.match(r"^ch\d{3}$", chapter_no):
        raise ValueError(f"章节号不匹配 ^ch\\d{{3}}$: {chapter_no!r}")
    if not reviewer_id:
        raise ValueError("审核员字段为空")

    aspects = _parse_aspects(sections.get("审核详情", ""))
    verdict = _parse_verdict(sections.get("审核结论", ""))
    issues = _parse_issues_table(sections.get("意见汇总", ""))

    return {
        "title": title,
        "chapter_no": chapter_no,
        "reviewer_id": reviewer_id,
        "verdict": verdict,
        "review_aspects": aspects,
        "issues": issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate 审核员报告 .md 结构。")
    ap.add_argument("paths", nargs="+", type=Path, help="审核报告 .md 路径")
    ap.add_argument("--quiet", action="store_true", help="成功后只打总数")
    args = ap.parse_args()

    errs = run_validator("reviewer_report", args.paths, load_fn=load_reviewer_report)
    return format_cli_errors(errs, quiet_success=args.quiet, n_files=len(args.paths))


if __name__ == "__main__":
    sys.exit(main())