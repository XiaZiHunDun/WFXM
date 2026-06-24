"""Sprint 10 TST-10-1: 删 apprise_adapter.py（消化 SEC-10-3 + Sprint 9 SEC-9.2 误报）

Sprint 10 TST-10-1 + SEC-10-3: butler/gateway/platforms/apprise_adapter.py 105 行
0 生产引用，整模块死代码。同时消化：
  - SEC-10-3 (Sprint 10 新报): apprise PII 未脱敏
  - SEC-9.2 (Sprint 9 误报): Sprint 9 报告标"已修"，实际未脱敏

修复：删除 1 个文件 + 4 个 TestAppriseAdapter 测试。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


APPRISE_ADAPTER = "butler/gateway/platforms/apprise_adapter.py"
TEST_FILE = "tests/test_dependency_extras.py"


@pytest.mark.unit
def test_apprise_adapter_module_does_not_exist(repo_root: Path):
    assert not (repo_root / APPRISE_ADAPTER).exists(), (
        f"死代码文件应被删除: {APPRISE_ADAPTER}"
    )


@pytest.mark.unit
def test_no_module_can_import_apprise_adapter():
    """删除后，被删模块应无法被 import（ModuleNotFoundError）。"""
    with pytest.raises(ModuleNotFoundError):
        __import__("butler.gateway.platforms.apprise_adapter")


@pytest.mark.unit
def test_test_dependency_extras_apprise_tests_removed(repo_root: Path):
    """tests/test_dependency_extras.py 中 TestAppriseAdapter 整类应已删。"""
    text = (repo_root / TEST_FILE).read_text(encoding="utf-8")
    assert "class TestAppriseAdapter" not in text, (
        "TestAppriseAdapter 整类应已删（4 个测试覆盖死代码）"
    )
    assert "apprise_adapter" not in text, (
        "test_dependency_extras.py 不再应 import apprise_adapter"
    )


@pytest.mark.unit
def test_production_code_does_not_import_apprise_adapter(repo_root: Path):
    """butler/ 下除被删模块自身外，应无 import apprise_adapter。"""
    py_files = list((repo_root / "butler").rglob("*.py"))
    hits = []
    for p in py_files:
        if p.name == "apprise_adapter.py":
            continue  # 被删模块自身
        text = p.read_text(encoding="utf-8")
        if re.search(r"from\s+butler\.gateway\.platforms\.apprise_adapter\s+import", text):
            hits.append(str(p.relative_to(repo_root)))
        if re.search(r"^import\s+butler\.gateway\.platforms\.apprise_adapter\b", text, re.M):
            hits.append(str(p.relative_to(repo_root)))
    assert not hits, f"仍有生产代码 import apprise_adapter: {hits}"


@pytest.mark.unit
def test_extras_test_extras_section_still_works(repo_root: Path):
    """extras 测试读 pyproject.toml，与删 apprise 适配器无关 — 应保留不删。"""
    text = (repo_root / TEST_FILE).read_text(encoding="utf-8")
    # extras 测试查 pyproject.toml 的 notify extras 是否含 apprise 包
    # apprise 仍可能在 pyproject extras 里（仅模块被删，extras 包保留无意义可后续清理）
    # 但该测试不再有 class 依赖
    assert "test_extras_contain_expected_packages" in text, (
        "extras 顶层测试应保留（仅 apprise 字符串检查可独立看）"
    )


@pytest.mark.unit
def test_no_prod_test_depends_on_apprise_module_symbols(repo_root: Path):
    """Sprint 9 SEC-9.2 误报"已修"，实际：本文档应成为唯一引用 apprise_adapter 的源。"""
    # 扫所有 .py（含本测试文件）
    all_py = list((repo_root / "butler").rglob("*.py")) + list((repo_root / "tests").rglob("*.py"))
    offenders = []
    for p in all_py:
        text = p.read_text(encoding="utf-8")
        if re.search(r"apprise_adapter|TestAppriseAdapter", text):
            # 本测试文件自身合法（验证删除）
            if p.name == "test_sprint10_tst1_apprise_removed.py":
                continue
            offenders.append(str(p.relative_to(repo_root)))
    assert not offenders, f"仍有 .py 引用 apprise_adapter 符号: {offenders}"
