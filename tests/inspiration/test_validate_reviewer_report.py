"""Tests for projects/LingWen1/novel-factory/tools/validators/validate_reviewer_report.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "tools"
    / "validators"
    / "validate_reviewer_report.py"
)
REAL_CH001_REPORT = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "06_意见仓库"
    / "04_正文_审核"
    / "ch001_审核员A_审核.md"
)


def _run(*paths: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, paths)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# ---- 模板：复制自真实 ch001_审核员A_审核.md，可参数化改造 ----
_GOOD_REPORT = """# ch001_审核员A_审核

## 章节信息
- **章节号**: ch001
- **标题**: 第一章 废土黄昏
- **审核员**: 审核员A
- **审核时间**: 2026-05-14

## 审核结论
**通过**

## 审核详情

### 逻辑一致性
- **结论**: 通过
- **说明**: 场景逻辑清晰。

### 人设稳定性
- **结论**: 通过
- **说明**: 主角设定稳定。

### 叙事节奏
- **结论**: 通过
- **说明**: 节奏紧凑。

### 章节连贯性
- **结论**: 通过
- **说明**: 首章作用明确。

## 意见汇总

| 优先级 | 问题类型 | 意见内容 |
|--------|---------|---------|
| P2 | 轻微优化 | 第101行可改 |
"""


@pytest.mark.unit
def test_real_ch001_reviewer_passes():
    """LingWen1 真实 ch001_审核员A_审核.md 应通过 schema。"""
    proc = _run(REAL_CH001_REPORT)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert "validated" in proc.stdout


@pytest.mark.unit
def test_good_template_passes(tmp_path):
    good = tmp_path / "good.md"
    good.write_text(_GOOD_REPORT, encoding="utf-8")
    proc = _run(good)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"


@pytest.mark.unit
def test_missing_aspect_fails(tmp_path):
    """删 ### 人设稳定性 → schema 缺 required key → exit 1。"""
    bad = tmp_path / "bad.md"
    bad.write_text(
        _GOOD_REPORT.replace(
            "### 人设稳定性\n- **结论**: 通过\n- **说明**: 主角设定稳定。\n\n",
            "",
        ),
        encoding="utf-8",
    )
    proc = _run(bad)
    assert proc.returncode == 1
    assert "人设稳定性" in proc.stderr


@pytest.mark.unit
def test_invalid_verdict_fails(tmp_path):
    """**勉强通过** 不在 enum → verdict 校验失败。"""
    bad = tmp_path / "bad.md"
    bad.write_text(_GOOD_REPORT.replace("**通过**", "**勉强通过**"), encoding="utf-8")
    proc = _run(bad)
    assert proc.returncode == 1
    assert "verdict" in proc.stderr


@pytest.mark.unit
def test_priority_out_of_enum_fails(tmp_path):
    """意见表加 P3 行 → priority enum 失败。"""
    bad = tmp_path / "bad.md"
    extra_row = "| P3 | 实验性 | 探索性意见 |\n"
    bad.write_text(_GOOD_REPORT.replace(
        "| P2 | 轻微优化 | 第101行可改 |",
        "| P2 | 轻微优化 | 第101行可改 |\n" + extra_row,
    ), encoding="utf-8")
    proc = _run(bad)
    assert proc.returncode == 1
    assert "P3" in proc.stderr or "priority" in proc.stderr