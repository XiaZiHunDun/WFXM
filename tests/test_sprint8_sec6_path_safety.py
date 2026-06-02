"""Sprint 8 audit fix: SEC-6 — path_safety str.startswith 越权

Sprint 8 SEC-6：`butler/tools/path_safety.py:268` 用 `str.startswith`
做路径包含检查，存在字符串前缀绕过：

  root = /tmp/foo
  target = /tmp/foo2/secrets.txt  →  str(target).startswith(str(root))
                                      判 True，错误放行

应改用 `Path.resolve().is_relative_to(root.resolve())`。
"""

from __future__ import annotations

import pytest

from butler.tools.path_safety import _resolve_tool_path


@pytest.mark.unit
def test_resolve_tool_path_rejects_sibling_prefix_bypass(tmp_path):
    """`/var/butler2` 不应被 `/var/butler` 放行 — Sprint 8 SEC-6 复检。

    字符串前缀匹配会把 root=/var/butler 与 target=/var/butler2/* 都判
    True，绕过 workspace 隔离。Path.is_relative_to 才能正确处理。

    模拟攻击：root 下放一个软链 → sibling 目录里的 secret。
    """
    root = tmp_path / "butler"
    sibling = tmp_path / "butler2"
    root.mkdir()
    sibling.mkdir()
    secret = sibling / "secrets.txt"
    secret.write_text("top secret", encoding="utf-8")
    symlink = root / "sneaky"
    symlink.symlink_to(secret)

    with pytest.raises(PermissionError) as exc_info:
        _resolve_tool_path(str(symlink), root)

    assert "outside workspace" in str(exc_info.value), (
        f"应被拒为 outside workspace，实际 {exc_info.value!r}"
    )


@pytest.mark.unit
def test_resolve_tool_path_allows_genuine_child(tmp_path):
    """真正的子路径仍应放行 — 防 fix 改坏主路径。"""
    root = tmp_path / "butler"
    root.mkdir()
    target = root / "subdir" / "ok.txt"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")

    resolved = _resolve_tool_path(str(target), root)

    assert resolved == target.resolve()


@pytest.mark.unit
def test_resolve_tool_path_allows_genuine_symlink_inside(tmp_path):
    """root 内部的真子目录软链仍应放行 — 防 fix 误伤合法 symlink。"""
    root = tmp_path / "butler"
    inner = root / "data"
    root.mkdir()
    inner.mkdir()
    secret = inner / "real.txt"
    secret.write_text("ok", encoding="utf-8")
    symlink = root / "link"
    symlink.symlink_to(secret)

    resolved = _resolve_tool_path(str(symlink), root)

    assert resolved == secret.resolve()
