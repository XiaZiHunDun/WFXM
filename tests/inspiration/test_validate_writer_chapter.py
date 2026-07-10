"""Tests for projects/LingWen1/novel-factory/tools/validators/validate_writer_chapter.py."""

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
    / "validate_writer_chapter.py"
)
REAL_CH001 = (
    ROOT / "projects" / "LingWen1" / "novel-factory" / "03_内容仓库" / "04_正文" / "ch001.md"
)


def _run(*paths: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, paths)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.unit
def test_real_ch001_passes():
    """LingWen1 真实 ch001.md 应通过当前 schema（无 frontmatter）。"""
    proc = _run(REAL_CH001)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert "validated" in proc.stdout


@pytest.mark.unit
def test_broken_h1_fails(tmp_path):
    """H1 不是 '# 第N章 标题' 形式 → exit 1。"""
    bad = tmp_path / "ch001.md"
    bad.write_text(
        "## 第二章 xx\n\n"
        "黄昏将整片天际染成暗红，像凝固的血。\n\n"
        "那颗陨星坠落的时候，林夜正蹲在窗边。\n\n"
        "他指着窗外那道划破苍穹的火光，稚嫩的声音里满是兴奋。\n\n"
        "父亲放下手中的猎刀，望向窗外。\n\n"
        "快走！父亲一把将猎刀握在手中。\n",
        encoding="utf-8",
    )
    proc = _run(bad)
    assert proc.returncode == 1
    assert "H1 不是" in proc.stderr


@pytest.mark.unit
def test_chapter_no_mismatch_fails(tmp_path):
    """filename ch999.md 但 H1 是 第一章 → 章节号不一致。"""
    bad = tmp_path / "ch999.md"
    bad.write_text(
        "# 第一章 废土黄昏\n\n"
        "黄昏将整片天际染成暗红，像凝固的血。\n\n"
        "那颗陨星坠落的时候，林夜正蹲在窗边。\n\n"
        "他指着窗外那道划破苍穹的火光。\n\n"
        "父亲放下手中的猎刀。\n\n"
        "快走！父亲一把将猎刀握在手中。\n",
        encoding="utf-8",
    )
    proc = _run(bad)
    assert proc.returncode == 1
    assert "章节号不一致" in proc.stderr


@pytest.mark.unit
def test_too_short_fails(tmp_path):
    """Stub 章节只有 1 段 → body_paragraphs/length_chars 下限触发。"""
    bad = tmp_path / "ch001.md"
    bad.write_text(
        "# 第一章 废土黄昏\n\n短短一句话。\n",
        encoding="utf-8",
    )
    proc = _run(bad)
    assert proc.returncode == 1
    # 期望至少命中 length_chars / body_paragraphs / required fields 中的一个
    assert any(
        marker in proc.stderr
        for marker in ("length_chars", "body_paragraphs", "500", "5")
    )