"""Tests for projects/LingWen1/novel-factory/tools/inspiration/validate_base_layer.py."""

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
    / "inspiration"
    / "validate_base_layer.py"
)
TEMPLATE = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "01_灵感库"
    / "模板库"
    / "基础层模板.yaml"
)


def _run(*paths: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, paths)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.unit
def test_template_file_passes():
    proc = _run(TEMPLATE)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"
    assert "validated" in proc.stdout


@pytest.mark.unit
def test_missing_required_fails(tmp_path):
    bad = tmp_path / "missing.yaml"
    bad.write_text("template_id: base_layer_v1\n", encoding="utf-8")
    proc = _run(bad)
    assert proc.returncode == 1
    assert "项目名称" in proc.stderr
    assert "is a required property" in proc.stderr


@pytest.mark.unit
def test_minimal_valid_yaml_passes(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(
        (
            "template_id: base_layer_v1\n"
            "项目名称: 测试小说\n"
            "类型: 玄幻\n"
            "主题: 测试主题\n"
            "类型定位: 东方玄幻\n"
            "核心卖点:\n"
            "  - 卖点 1\n"
            "  - 卖点 2\n"
            "  - 卖点 3\n"
            "核心人物:\n"
            "  主角:\n"
            "    名称: 林夜\n"
            "    身份: 少年\n"
            "    性格: 内敛\n"
            "    核心诉求: 守护\n"
            "风格禁忌:\n"
            "  - 不降智\n"
        ),
        encoding="utf-8",
    )
    proc = _run(good)
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}"


@pytest.mark.unit
def test_less_than_three_selling_points_fails(tmp_path):
    bad = tmp_path / "few.yaml"
    bad.write_text(
        (
            "template_id: base_layer_v1\n"
            "项目名称: x\n"
            "类型: 玄幻\n"
            "主题: x\n"
            "类型定位: x\n"
            "核心卖点:\n"
            "  - 卖点 1\n"
            "核心人物:\n"
            "  主角:\n"
            "    名称: x\n"
            "    身份: x\n"
            "    性格: x\n"
            "    核心诉求: x\n"
            "风格禁忌:\n"
            "  - x\n"
        ),
        encoding="utf-8",
    )
    proc = _run(bad)
    assert proc.returncode == 1
    assert "核心卖点" in proc.stderr


@pytest.mark.unit
def test_protagonist_missing_required_field_fails(tmp_path):
    bad = tmp_path / "no_name.yaml"
    bad.write_text(
        (
            "template_id: base_layer_v1\n"
            "项目名称: x\n"
            "类型: x\n"
            "主题: x\n"
            "类型定位: x\n"
            "核心卖点:\n"
            "  - a\n"
            "  - b\n"
            "  - c\n"
            "核心人物:\n"
            "  主角:\n"
            "    身份: x\n"
            "    性格: x\n"
            "    核心诉求: x\n"
            "风格禁忌:\n"
            "  - x\n"
        ),
        encoding="utf-8",
    )
    proc = _run(bad)
    assert proc.returncode == 1
    assert "名称" in proc.stderr


@pytest.mark.unit
def test_yaml_parse_error_reported(tmp_path):
    bad = tmp_path / "broken.yaml"
    bad.write_text("{not valid yaml", encoding="utf-8")
    proc = _run(bad)
    assert proc.returncode == 1
    assert "YAML 解析失败" in proc.stderr