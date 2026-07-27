"""G2: Shim 文件 __all__ 稳定性测试。

验证 shim 文件（带 DeprecationWarning 的向后兼容层）的 __all__
与对应包的 __all__ 一致。AI 工具误改 shim 的 __all__ 会破坏
其他模块的 import，导致运行时 ImportError。

shim 文件清单见 butler/ 下所有以 "Deprecated: Use ... package instead."
开头的 .py 文件。
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BUTLER_DIR = REPO_ROOT / "butler"


def _is_shim(file_path: Path) -> bool:
    """检查文件是否为 shim 文件（开头包含 Deprecated: ... package instead.）"""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        # shim 文件的 docstring 包含 "Deprecated: Use ... package instead."
        return "Deprecated:" in content and "package instead." in content
    except OSError:
        return False


def _extract_all(file_path: Path) -> list[str] | None:
    """从 .py 文件中提取 __all__ 列表（AST 解析）。"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except (OSError, SyntaxError):
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, ast.List):
                        return [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
    return None


def _find_shim_files() -> list[Path]:
    """查找所有 shim 文件。"""
    shims: list[Path] = []
    for py_file in BUTLER_DIR.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        if _is_shim(py_file):
            shims.append(py_file)
    return shims


def _shim_to_package_module(shim_path: Path) -> str | None:
    """从 shim 文件路径推断对应的包模块名。

    例如 butler/skills/manager.py → butler.skills.manager (包)
    """
    try:
        rel = shim_path.relative_to(REPO_ROOT)
    except ValueError:
        return None

    parts = rel.parts
    if not parts or parts[0] != "butler":
        return None

    # butler/skills/manager.py → butler.skills.manager (与文件同名但作为包导入)
    module_path = ".".join(parts[:-1]) + "." + parts[-1][:-3]  # 去掉 .py
    return module_path


SHIM_FILES = _find_shim_files()


@pytest.mark.parametrize("shim_path", SHIM_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_shim_all_matches_package_all(shim_path: Path):
    """Shim 文件的 __all__ 必须与对应包的 __all__ 一致。"""
    shim_all = _extract_all(shim_path)
    if shim_all is None:
        pytest.fail(f"Shim 文件 {shim_path.name} 缺少 __all__ 定义")

    package_module = _shim_to_package_module(shim_path)
    if package_module is None:
        pytest.skip(f"无法推断 {shim_path.name} 对应的包模块名")

    try:
        pkg = importlib.import_module(package_module)
    except ImportError as e:
        pytest.skip(f"无法导入包 {package_module}: {e}")

    package_all = getattr(pkg, "__all__", None)
    if package_all is None:
        pytest.fail(f"包 {package_module} 缺少 __all__ 定义")

    shim_set = set(shim_all)
    package_set = set(package_all)

    missing_in_shim = package_set - shim_set
    extra_in_shim = shim_set - package_set

    assert not missing_in_shim, (
        f"Shim {shim_path.name} 的 __all__ 缺少包 {package_module} 的导出: {missing_in_shim}"
    )
    assert not extra_in_shim, (
        f"Shim {shim_path.name} 的 __all__ 有包 {package_module} 未导出的项: {extra_in_shim}"
    )


def test_shim_files_count():
    """Shim 文件数量不应低于基线（防止 AI 误删 shim）。"""
    count = len(SHIM_FILES)
    # 基线：截至 2026-07-21 有 7 个 shim 文件
    assert count >= 7, (
        f"Shim 文件数量异常：当前 {count} 个，基线 7 个。"
        f"Shim 文件不应被删除，可能被 AI 误删。"
    )
