"""Sprint 21-1 SEC-21-A-1: `path_outside_workspace` startswith 越界 (CRITICAL).

`butler/permissions/rules.py:97` 用
`return not str(target).startswith(str(root))` 校验路径越界, **没**加
`os.sep` 后缀. 与 Sprint 19-2 SEC-19-A-3 `uninstall_skill` (line 194)
写的是 `startswith(str(root_resolved) + os.sep)` (正确) 风格不统一,
而且 rules.py 这条是裸 startswith, 漏判:

1) sibling-prefix: workspace = /tmp/proj, target = /tmp/proj_evil/x.md
   会被 `str(target).startswith(str(root))` 误判为 inside (True),
   而真实语义是 outside. 后果: read_file / write_file / patch / delete_file
   等 path tool 允许访问任意 sibling-prefix 目录, 越权读 / 改写.

2) macOS /tmp symlink: /tmp -> /private/tmp, `workspace.resolve()` /
   `target.resolve()` 已 follow, 但若未来某处漏掉 .resolve() (回归),
   startswith 会把 "/tmp/proj" 跟 "/private/tmp/proj" 字符串比, 返 False
   (误判 outside), fail-open 误拒合法路径.

3) Windows 大小写不敏感 + drive letter + UNC 前缀: 字符串级 startswith
   全部漏判. `Path.is_relative_to` (3.9+) 做 path component 级比较,
   跨平台一致.

修复: 用 `target.is_relative_to(root)` 替换 startswith. 镜像
Sprint 20-3 quarantine_bundle 修复 (Sprint 21-4 uninstall_skill
也用 is_relative_to 进一步统一, 详见 test_sprint21_qual_d2).

行为保证:
1) sibling-prefix 路径必须判为 outside
2) workspace 子文件判为 inside (无回归)
3) 无关路径 (workspace 之外) 判为 outside
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.permissions.rules import path_outside_workspace
from butler.tools.path_safety import PathSafetyResult


def _allow_all() -> PathSafetyResult:
    """Return a PathSafetyResult that lets the call proceed to the startswith check.

    `check_tool_path` is called first inside `path_outside_workspace`. If
    it returns `allowed=True`, the code falls through to the bare startswith
    check we are auditing. We use this stub to isolate the buggy line.
    """
    return PathSafetyResult(allowed=True, path=Path("/"), error="")


@pytest.mark.unit
class TestStaticContract:
    """`path_outside_workspace` 必须用 `Path.is_relative_to`, 不能再用裸 startswith."""

    def test_uses_is_relative_to(self):
        from butler.permissions import rules

        src = inspect.getsource(rules.path_outside_workspace)
        # 剥掉注释行避免误命中 (Sprint 21-1 注释里会提 startswith)
        code_lines = [
            line for line in src.splitlines() if not line.strip().startswith("#")
        ]
        code_src = "\n".join(code_lines)
        assert "is_relative_to" in code_src, (
            "path_outside_workspace 必须用 Path.is_relative_to 防 path traversal, "
            f"实际源码片段:\n{src}"
        )
        # 防止 startswith 残留: 不能再用 `startswith(str(root` (rules.py 特有)
        assert "startswith(str(root" not in code_src, (
            "path_outside_workspace 不应再用裸 startswith 检查越界, "
            f"实际源码:\n{src}"
        )

    def test_does_not_use_bare_startswith(self):
        from butler.permissions import rules

        src = inspect.getsource(rules.path_outside_workspace)
        code_lines = [
            line for line in src.splitlines() if not line.strip().startswith("#")
        ]
        code_src = "\n".join(code_lines)
        # 严格: 整个函数不应再用 .startswith( 做越界检查
        # (允许注释中保留 .startswith 字面引用)
        assert ".startswith(" not in code_src, (
            "path_outside_workspace 应只保留 is_relative_to 作为越界检查, "
            f"实际源码:\n{src}"
        )


@pytest.mark.unit
class TestPathOutsideWorkspaceBehavior:
    """行为验证: sibling-prefix 必须被判为 outside, 子路径 inside."""

    def test_sibling_prefix_path_is_outside(self, tmp_path: Path):
        """workspace=/tmp/proj, target=/tmp/proj_evil/x.md → outside (current 误判 inside).

        构造: tmp_path = "/tmp/abc", workspace = "/tmp/abc/proj",
        target 父目录 = "/tmp/abc/proj_evil". 字符串 "proj_evil".startswith("proj")
        为 True, 触发 startswith false positive.
        """
        workspace = tmp_path / "proj"
        workspace.mkdir()
        sibling = tmp_path / "proj_evil"
        sibling.mkdir()
        target = sibling / "x.md"
        target.write_text("evil", encoding="utf-8")

        with patch(
            "butler.tools.path_safety.check_tool_path",
            return_value=_allow_all(),
        ):
            result = path_outside_workspace(str(target), workspace)
        assert result is True, (
            f"sibling-prefix {target} 应被判为 outside workspace {workspace}, "
            f"实际 result={result} (sibling 目录名是 workspace 的前缀, "
            f"裸 startswith 会漏判)"
        )

    def test_inside_workspace_path_is_not_outside(self, tmp_path: Path):
        """workspace=/tmp/proj, target=/tmp/proj/file.md → inside."""
        workspace = tmp_path / "proj"
        workspace.mkdir()
        target = workspace / "file.md"
        target.write_text("ok", encoding="utf-8")

        with patch(
            "butler.tools.path_safety.check_tool_path",
            return_value=_allow_all(),
        ):
            result = path_outside_workspace(str(target), workspace)
        assert result is False, (
            f"workspace 子文件 {target} 应被判为 inside, 实际 result={result}"
        )

    def test_parent_path_is_outside(self, tmp_path: Path):
        """workspace=/tmp/proj, target=/tmp/other/x.md → outside."""
        workspace = tmp_path / "proj"
        workspace.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        target = other / "x.md"
        target.write_text("x", encoding="utf-8")

        with patch(
            "butler.tools.path_safety.check_tool_path",
            return_value=_allow_all(),
        ):
            result = path_outside_workspace(str(target), workspace)
        assert result is True, (
            f"完全无关路径 {target} 应被判为 outside, 实际 result={result}"
        )

    def test_nested_subdir_inside_workspace(self, tmp_path: Path):
        """workspace=/tmp/proj, target=/tmp/proj/a/b/c.md → inside (嵌套)."""
        workspace = tmp_path / "proj"
        workspace.mkdir()
        nested = workspace / "a" / "b"
        nested.mkdir(parents=True)
        target = nested / "c.md"
        target.write_text("nested", encoding="utf-8")

        with patch(
            "butler.tools.path_safety.check_tool_path",
            return_value=_allow_all(),
        ):
            result = path_outside_workspace(str(target), workspace)
        assert result is False, (
            f"嵌套子文件 {target} 应被判为 inside, 实际 result={result}"
        )


@pytest.mark.unit
class TestEdgeCases:
    """边界情况."""

    def test_empty_path_returns_false(self, tmp_path: Path):
        """空 path_str → 返回 False (无 path 无越界, by-design)."""
        workspace = tmp_path / "proj"
        workspace.mkdir()
        # No mock needed: empty string short-circuits at the top.
        result = path_outside_workspace("", workspace)
        assert result is False, (
            f"空 path 应返回 False (无 path 无越界), 实际 result={result}"
        )

    def test_relative_path_resolved_against_workspace(self, tmp_path: Path):
        """相对 path 解析到 workspace 内 → inside."""
        workspace = tmp_path / "proj"
        workspace.mkdir()
        sub = workspace / "src"
        sub.mkdir()

        with patch(
            "butler.tools.path_safety.check_tool_path",
            return_value=_allow_all(),
        ):
            # 'src/main.py' 解析为 workspace/src/main.py, 应 inside
            result = path_outside_workspace("src/main.py", workspace)
        assert result is False, (
            f"相对路径 'src/main.py' 应解析为 workspace 子路径 → inside, "
            f"实际 result={result}"
        )
