"""Sprint 21-4 QUAL-21-D-2: `uninstall_skill` 越界检查统一 `is_relative_to`.

`butler/registry/skill_install.py:194` `uninstall_skill` 当前用
`str(content_resolved).startswith(str(root_resolved) + os.sep)`
校验 content_path 越界. 这是**正确**形式 (有 os.sep 后缀, 防
sibling-prefix), 但与 codebase 其它位置风格不统一:

- `quarantine_bundle` (skill_install.py:62, Sprint 20-3 修): `is_relative_to`
- `_path_outside_workspace` (permissions/rules.py:97, Sprint 21-1 修): `is_relative_to`
- `uninstall_skill` (skill_install.py:194, **本 Sprint 修**): startswith + os.sep

统一为 `is_relative_to` 的好处:
1. 跨平台一致 (POSIX / Windows / macOS /tmp symlink 全 OK)
2. 减少漂移 (codebase 内单一路越界检查 pattern)
3. 跟标准库 (Python 3.9+) 一致, 读者无需思考 sep 边界

`is_relative_to` 与 `startswith(str(x) + os.sep)` 在语义上等价
(对 resolved path 而言), 但更直观. 此 fix 改写为 is_relative_to
后, 行为保持一致 (traversal 仍被拒, 合法 content_path 仍通过).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from butler.registry.skill_install import uninstall_skill


@pytest.mark.unit
class TestStaticContract:
    """`uninstall_skill` 必须用 `Path.is_relative_to`, 不能再用 startswith + os.sep."""

    def test_uses_is_relative_to(self):
        """uninstall_skill 源码必须含 `is_relative_to` 调用."""
        from butler.registry import skill_install

        src = inspect.getsource(skill_install.uninstall_skill)
        # 剥掉注释行避免误命中
        code_lines = [
            line for line in src.splitlines() if not line.strip().startswith("#")
        ]
        code_src = "\n".join(code_lines)
        assert "is_relative_to" in code_src, (
            "uninstall_skill 必须用 Path.is_relative_to 越界检查, "
            f"实际源码片段:\n{src}"
        )

    def test_does_not_use_startswith_for_traversal_check(self):
        """源码不能含 `startswith(str(...).resolve()) + os.sep` 越界检查."""
        from butler.registry import skill_install

        src = inspect.getsource(skill_install.uninstall_skill)
        code_lines = [
            line for line in src.splitlines() if not line.strip().startswith("#")
        ]
        code_src = "\n".join(code_lines)
        # 不能有 `.startswith(str(` 这种 string 越界检查 (允许其它 startswith)
        assert ".startswith(str(" not in code_src, (
            "uninstall_skill 不应再用 startswith(str(...)) 越界检查, "
            f"应统一用 Path.is_relative_to. 实际源码:\n{src}"
        )

    def test_does_not_use_os_sep_concat(self):
        """不能有 `+ os.sep` 字符串拼接 (典型 startswith 越界检查痕迹)."""
        from butler.registry import skill_install

        src = inspect.getsource(skill_install.uninstall_skill)
        code_lines = [
            line for line in src.splitlines() if not line.strip().startswith("#")
        ]
        code_src = "\n".join(code_lines)
        assert "+ os.sep" not in code_src, (
            "uninstall_skill 不应再用 startswith + os.sep 越界检查, "
            f"应统一用 Path.is_relative_to. 实际源码:\n{src}"
        )


@pytest.mark.unit
class TestUninstallSkillBehavior:
    """行为验证: 越界被拒, 合法 content_path 通过."""

    def _setup_skill(self, root: Path, name: str, content_rel: str) -> Path:
        """Helper: 在 skills_root/<name>.md 写一个带 content_path 的 stub."""
        root.mkdir(parents=True, exist_ok=True)
        stub = root / f"{name}.md"
        # content_rel is relative to skills root
        if content_rel:
            stub.write_text(
                f"---\n"
                f"name: {name}\n"
                f"install_type: directory\n"
                f"content_path: {content_rel}\n"
                f"---\n",
                encoding="utf-8",
            )
        else:
            stub.write_text(
                f"---\nname: {name}\n---\n",
                encoding="utf-8",
            )
        return stub

    def _write_lock(self, root: Path, name: str, install_path: str) -> None:
        """Write a lock file so uninstall_skill can find the record."""
        from butler.registry.skill_lock import SkillLockFile
        from butler.registry.skill_types import InstalledSkillRecord

        lock = SkillLockFile(path=root / ".skill_lock.json")
        lock.record_install(
            InstalledSkillRecord(
                name=name,
                source="hub",
                identifier=f"{name}@1.0.0",
                version="1.0.0",
                installed_at="2026-06-04T00:00:00Z",
                content_hash="abc",
                install_path=install_path,
                scan_verdict="ok",
                trust="community",
            )
        )

    def test_traversal_content_path_rejected(self, tmp_path: Path, monkeypatch):
        """content_path 越界 (e.g. ../../../etc/passwd) → uninstall 拒绝.

        直接触发越界检查需要 lock file + stub 配合. 简化: 把 root 指向
        一个子目录, 构造 content_path 指向父目录的兄弟, 验证 is_relative_to
        正确拒绝.
        """
        # Setup: skills_root 在 tmp_path/skills, lock + stub 都在
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        name = "evil-skill"
        self._setup_skill(skills_root, name, "../../escape.md")
        self._write_lock(skills_root, name, f"{name}.md")

        # Patch skills_root to point at our tmp dir
        from butler.registry import skill_install
        from butler.registry import paths as paths_mod

        monkeypatch.setattr(paths_mod, "skills_root", lambda tenant_id="": skills_root)
        # Also need to handle skill_install's reference (it imports directly)
        monkeypatch.setattr(skill_install, "skills_root", lambda tenant_id="": skills_root)

        ok, msg = uninstall_skill(name)
        assert ok is False, f"越界 content_path 应被拒, 实际 ok={ok}, msg={msg!r}"
        assert "unsafe" in msg.lower() or "outside" in msg.lower() or "path" in msg.lower(), (
            f"错误信息应提及越界, 实际: {msg!r}"
        )

    def test_legitimate_content_path_passes(self, tmp_path: Path, monkeypatch):
        """合法 content_path (skills_root 内) → 卸载成功, 清理目录."""
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        name = "good-skill"
        # content_path 在 skills_root 内
        content_dir_rel = f"{name}_dir"
        self._setup_skill(skills_root, name, content_dir_rel)
        # 写一个 content_path 指向的目录 + 文件
        content_dir = skills_root / content_dir_rel
        content_dir.mkdir()
        (content_dir / "main.md").write_text("body", encoding="utf-8")
        self._write_lock(skills_root, name, f"{name}.md")

        from butler.registry import skill_install
        from butler.registry import paths as paths_mod

        monkeypatch.setattr(paths_mod, "skills_root", lambda tenant_id="": skills_root)
        monkeypatch.setattr(skill_install, "skills_root", lambda tenant_id="": skills_root)

        ok, msg = uninstall_skill(name)
        assert ok is True, f"合法 content_path 应卸载成功, 实际 ok={ok}, msg={msg!r}"
        # stub 文件应被删除
        assert not (skills_root / f"{name}.md").exists(), (
            f"卸载后 stub 文件应被删除, 实际: {list(skills_root.iterdir())}"
        )
