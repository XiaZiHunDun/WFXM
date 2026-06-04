"""Sprint 19-2: uninstall_skill path traversal 修复 (Sprint 19 subagent A SEC-19-A-3).

Sprint 19 subagent A 安全审计: _content_path_from_stub 读 skill frontmatter
content_path 不做边界检查. uninstall_skill line 184 `content_file = root / content_rel`
+ line 188 `shutil.rmtree(skill_dir, ignore_errors=True)` 会被恶意 skill frontmatter
利用. 若 content_path = `../../../tmp/important`, 卸载时 shutil.rmtree 会**递归删除
root 外的任意目录** (root = ~/.butler/skills/<tenant>).

攻击面: 任何能让恶意 skill 进入 registry 的路径 (含 owner gate 修复前的窗口期
+ 未来 content_path 写入未 sanitized 的 skill).

修复: 在 uninstall_skill 删除前, 验证 content_file.resolve() 必须在 root.resolve() 内.
content_path 越界 → 返 (False, error), 不删任何文件.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.registry.skill_install import uninstall_skill


def _make_skill_with_content_path(
    root: Path, name: str, content_path_value: str
) -> None:
    """Create a skill lock entry + stub .md with given content_path in frontmatter.

    Mirrors install_from_quarantine layout:
        stub   = root/{name}.md              (dest)
        skill_dir = root/{name}/             (sibling, holds content_file)
    uninstall_skill looks for stub at root/{name}.md per install_path.
    """
    root.mkdir(parents=True, exist_ok=True)
    stub = root / f"{name}.md"
    stub.write_text(
        textwrap.dedent(f"""\
        ---
        install_type: directory
        content_path: {content_path_value}
        ---
        # {name}
        """),
        encoding="utf-8",
    )
    from butler.registry.skill_lock import SkillLockFile

    lock = SkillLockFile(tenant_id="default")
    lock.record_install(
        type("R", (), {
            "name": name,
            "identifier": f"test/{name}",
            "source": "test",
            "version": "1.0",
            "installed_at": "2026-06-04T00:00:00Z",
            "content_hash": "",
            "install_path": f"{name}.md",
            "scan_verdict": "clean",
            "trust": "builtin",
        })()
    )


@pytest.mark.unit
class TestPathTraversalBlocked:
    """Sprint 19-2 SEC-19-A-3: content_path 越界 → 拒绝卸载."""

    def test_relative_parent_traversal_rejected(self, tmp_path, monkeypatch):
        """content_path: ../../../tmp/important → 拒绝, 不删 root 外目录."""
        # 模拟 root = ~/.butler/skills/default, content_path 越界到 /tmp/important
        # 实际验证: 不应触发 shutil.rmtree 到 tmp_path 之外
        outside_dir = tmp_path / "outside_target"
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("DO NOT DELETE", encoding="utf-8")

        # content_path 相对 root 跳出再进入 outside_dir
        # root = tmp_path/skills_root, content_path = "../outside_target"
        root = tmp_path / "skills_root"
        root.mkdir()
        monkeypatch.setattr(
            "butler.registry.skill_install.skills_root", lambda tenant_id="": root
        )
        _make_skill_with_content_path(root, "evil-skill", "../outside_target")

        ok, msg = uninstall_skill("evil-skill", tenant_id="default")

        assert ok is False, f"越界 content_path 应拒绝卸载, 实际: {msg}"
        assert "unsafe" in msg.lower() or "拒绝" in msg or "refus" in msg.lower(), (
            f"错误消息应说明不安全: {msg}"
        )
        # outside_file 必须仍在 — 不能被 rmtree 删
        assert outside_file.exists(), (
            "越界 content_path 触发 rmtree 删除了 root 外的文件 — 漏洞未修复"
        )
        assert outside_file.read_text(encoding="utf-8") == "DO NOT DELETE"

    def test_absolute_path_rejected(self, tmp_path, monkeypatch):
        """/etc/passwd 形式的绝对路径 content_path → 拒绝."""
        # 注: Path("/etc/passwd") 用 .resolve() 后是绝对路径, 不在 root 内
        root = tmp_path / "skills_root"
        root.mkdir()
        monkeypatch.setattr(
            "butler.registry.skill_install.skills_root", lambda tenant_id="": root
        )
        _make_skill_with_content_path(root, "abs-skill", "/etc/passwd")

        ok, msg = uninstall_skill("abs-skill", tenant_id="default")
        assert ok is False, f"绝对路径 content_path 应拒绝, 实际: {msg}"


@pytest.mark.unit
class TestLegitimateContentPathStillWorks:
    """合法 content_path (root 内) 不被误拒."""

    def test_relative_path_inside_root_works(self, tmp_path, monkeypatch):
        """content_path: subdir/file.md (root 内) → 正常卸载, 不误拒."""
        root = tmp_path / "skills_root"
        root.mkdir()
        monkeypatch.setattr(
            "butler.registry.skill_install.skills_root", lambda tenant_id="": root
        )
        # content 在子目录, 触发原代码的 rmtree 路径 (skill_dir = content_file.parent)
        content_subdir = root / "good-skill-content"
        content_subdir.mkdir()
        content_file = content_subdir / "data.md"
        content_file.write_text("payload", encoding="utf-8")
        _make_skill_with_content_path(root, "good-skill", "good-skill-content/data.md")

        ok, msg = uninstall_skill("good-skill", tenant_id="default")

        assert ok is True, f"root 内合法 content_path 不应被拒: {msg}"
        assert "unsafe" not in msg.lower() and "拒绝" not in msg and "refus" not in msg.lower(), (
            f"root 内 content_path 不应触发 'unsafe'/'拒绝' 误报: {msg}"
        )

    def test_no_content_path_works(self, tmp_path, monkeypatch):
        """无 content_path (空 frontmatter 字段) → 正常卸载."""
        root = tmp_path / "skills_root"
        root.mkdir()
        monkeypatch.setattr(
            "butler.registry.skill_install.skills_root", lambda tenant_id="": root
        )
        _make_skill_with_content_path(root, "no-content", "")

        ok, msg = uninstall_skill("no-content", tenant_id="default")
        assert ok is True, f"无 content_path 不应被拒: {msg}"


@pytest.mark.unit
class TestStaticContract:
    """静态契约: uninstall_skill 内必须做 path 边界检查."""

    def test_path_traversal_guard_present(self):
        """uninstall_skill 必须含 path 边界检查 (resolve + startswith)."""
        import inspect
        from butler.registry import skill_install

        src = inspect.getsource(skill_install.uninstall_skill)
        assert ".resolve()" in src, "path 边界检查需 .resolve() 解析"
        assert "startswith" in src, "path 边界检查需 startswith 验证在 root 内"
