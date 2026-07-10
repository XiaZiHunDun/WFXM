#!/usr/bin/env python3
"""Validate 作家章节 .md against writer_chapter.schema.json.

用法:
    python validate_writer_chapter.py ch001.md [ch002.md ...]

解析流程:
  1. 验文件名 ^ch\\d{3}\\.md$
  2. 抽首行 H1（# 第N章 标题），验 pattern
  3. 中文数字 → 阿拉伯数字转换，与文件名 NNN 比对
  4. 段落切分（连续 ≥1 空行分隔），数 paragraph + 总 char
  5. 可选 frontmatter：检测文件首部 --- 块；存在则 YAML load；缺则 null
  6. 构造 dict → run_validator（jsonschema Draft 2020-12）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _base import format_cli_errors, run_validator

_ZH_DIGITS = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_FN_RE = re.compile(r"^ch(\d{3})\.md$")
_H1_RE = re.compile(r"^#\s*第([零一二三四五六七八九十百千]+)章\s+(.+)$")


def _zh_to_int(zh: str) -> int | None:
    """中文数字 → 阿拉伯数字。支持 零/一..九/十/百/千；'二十三' = 23, '三百零五' = 305。

    返回 None 表示含非法字符。
    """
    if not zh:
        return None
    if zh == "零":
        return 0
    total = 0
    cur = 0
    for c in zh:
        if c == "千":
            if cur == 0:
                return None
            total += cur * 1000
            cur = 0
        elif c == "百":
            if cur == 0:
                return None
            total += cur * 100
            cur = 0
        elif c == "十":
            total += (cur or 1) * 10
            cur = 0
        else:
            d = _ZH_DIGITS.get(c)
            if d is None:
                return None
            cur = cur * 10 + d
    return total + cur


def load_chapter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")

    fname = path.name
    fn_match = _FN_RE.match(fname)
    if not fn_match:
        raise ValueError(f"filename 不匹配 ^ch\\d{{3}}\\.md$: {fname}")
    fname_no = int(fn_match.group(1))

    first_line = text.split("\n", 1)[0]
    h1_match = _H1_RE.match(first_line)
    if not h1_match:
        raise ValueError(f"H1 不是 '# 第N章 标题' 形式: {first_line[:60]!r}")
    zh_no = h1_match.group(1)
    ch_no = _zh_to_int(zh_no)
    if ch_no is None:
        raise ValueError(f"H1 中文数字解析失败: 第{zh_no}章")
    if ch_no != fname_no:
        raise ValueError(
            f"章节号不一致: 文件 {fname} (={fname_no}) vs H1 第{ch_no}章"
        )

    frontmatter = None
    body_start = 0
    if text.startswith("---\n"):
        fm_match = _FM_RE.match(text)
        if fm_match:
            try:
                import yaml
            except ImportError:
                raise RuntimeError(
                    "检测到 frontmatter 但缺 PyYAML；请 pip install pyyaml"
                )
            frontmatter = yaml.safe_load(fm_match.group(1)) or None
            body_start = fm_match.end()

    body = text[body_start:]
    paragraphs = [p for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]

    return {
        "filename": fname,
        "h1_heading": first_line.lstrip("#").strip(),
        "body_paragraphs": len(paragraphs),
        "length_chars": len(text),
        "chapter_no_consistent": True,
        "frontmatter": frontmatter,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate 作家章节 .md 结构。")
    ap.add_argument("paths", nargs="+", type=Path, help="章节 .md 路径")
    ap.add_argument("--quiet", action="store_true", help="成功后只打总数")
    args = ap.parse_args()

    errs = run_validator("writer_chapter", args.paths, load_fn=load_chapter)
    return format_cli_errors(errs, quiet_success=args.quiet, n_files=len(args.paths))


if __name__ == "__main__":
    sys.exit(main())