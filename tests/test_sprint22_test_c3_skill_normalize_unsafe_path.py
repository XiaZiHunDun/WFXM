"""Sprint 22-6 TEST-21-C-3: `bundle_install_layout` 路径遍历 via 绝对路径 / Windows-drive.

`butler/registry/skill_normalize.py:89-94` `_safe_rel_path` 只过滤
`..` 段, **不拒绝绝对路径或 Windows 盘符**. 恶意 skill bundle
含 `{"c:/evil.md": "..."}` (suffix `.md` 在 `_ALLOWED_SUFFIXES`)
被 normalize 后变成 `c:/evil.md` (单段, 无 `..`), 进入
`dir_files`, 目录安装器 (skill_install.py 下游) 会写到
`<skills_root>/<name>/c:/evil.md` (POSIX, 字面 `c:` 子目录
— 怪但不出 root) 或 **逃出 root 到 `C:\\evil.md`** (Windows,
盘符解析).

更直接的: `{"SKILL.md": ..., "/etc/passwd": "..."}` 经 lstrip
`/` 后变成 `"etc/passwd"`, 通过 `_safe_rel_path` 落到
`<skills_root>/<name>/etc/passwd` — POSIX 也不出 root,
但语义上仍是攻击.

修复: `_safe_rel_path` 必须拒绝:
1. 绝对 POSIX 路径 (以 `/` 起)
2. Windows 盘符 (`c:`, `d:`, ... 段, 任何大小写)
3. 顶层 backslash (虽然 replace \\ -> / 已处理, 加个 defense in depth)

行为保证 (本测试):
1) 相对路径 "reference.md" / "sub/note.md" 仍通过 (happy path)
2) ".." / "../escape.md" 仍被拒 (旧行为保留)
3) "/etc/passwd" / "\\\\server\\share" 风格的绝对路径被拒
4) "c:/evil.md" / "C:\\evil.md" / "Z:secret" 风格的盘符被拒
5) 上述被拒的 key **不进 `dir_files`**, 但 SKILL.md 主文件仍正常
   install (防御性 — 不让一个坏 key 弄死整个 bundle)
6) 没有 .md 键时, 旧行为: 抛 "Bundle has no .md skill file" 保留
"""

from __future__ import annotations

import pytest

from butler.registry.skill_normalize import (
    _safe_rel_path,
    bundle_install_layout,
)


# ---------- direct _safe_rel_path tests ----------

@pytest.mark.unit
class TestSafeRelPathRejectsAbsoluteAndDrive:
    """`_safe_rel_path` 必须拒绝绝对路径 + Windows 盘符."""

    def test_relative_path_passes(self):
        """普通相对路径继续工作 (happy path 保留)."""
        assert _safe_rel_path("reference.md") == "reference.md"
        assert _safe_rel_path("sub/note.md") == "sub/note.md"
        assert _safe_rel_path("deep/nested/file.md") == "deep/nested/file.md"

    def test_dotdot_rejected(self):
        """`..` 段仍被拒 (旧行为)."""
        assert _safe_rel_path("../escape.md") is None
        assert _safe_rel_path("a/../b.md") is None

    def test_empty_rejected(self):
        """空 / 纯 `..` 仍被拒."""
        assert _safe_rel_path("") is None
        assert _safe_rel_path("..") is None
        assert _safe_rel_path(".") is None

    def test_posix_absolute_rejected(self):
        """POSIX 绝对路径 `/etc/passwd` 必须被拒."""
        assert _safe_rel_path("/etc/passwd") is None, (
            f"POSIX 绝对路径 /etc/passwd 应被拒, "
            f"实际 _safe_rel_path 返回值: {_safe_rel_path('/etc/passwd')!r}"
        )
        assert _safe_rel_path("/var/log/auth") is None

    def test_windows_drive_letter_rejected(self):
        """Windows 盘符 c:/, C:/, Z: 必须被拒 (escape root 风险)."""
        assert _safe_rel_path("c:/evil.md") is None, (
            f"Windows 盘符 c:/evil.md 应被拒, 实际: {_safe_rel_path('c:/evil.md')!r}"
        )
        assert _safe_rel_path("C:/evil.md") is None
        assert _safe_rel_path("Z:secret") is None  # 单段, 但有盘符

    def test_windows_backslash_drive_rejected(self):
        """Windows 反斜杠路径 `C:\\evil.md` 必须被拒 (replace \\ -> / 之后仍有 C: 段)."""
        backslash_path = "C:\\evil.md"
        assert _safe_rel_path(backslash_path) is None, (
            f"反斜杠盘符路径应被拒, 实际: {_safe_rel_path(backslash_path)!r}"
        )
        assert _safe_rel_path("d:\\path\\file.md") is None

    def test_drive_letter_any_case(self):
        """盘符检查必须 case-insensitive (Windows 路径不区分大小写)."""
        for prefix in ("a:", "Z:", "M:", "x:"):
            assert _safe_rel_path(f"{prefix}/file.md") is None, (
                f"盘符 {prefix} 应被拒, 实际: {_safe_rel_path(prefix + '/file.md')!r}"
            )


# ---------- integration: bundle_install_layout ----------

@pytest.mark.unit
class TestBundleInstallLayoutRejectsUnsafeKeys:
    """`bundle_install_layout` 实际必须过滤不安全 key."""

    def test_drive_letter_key_excluded_from_dir_files(self):
        """`c:/evil.md` 键不进 `dir_files`, SKILL.md 仍正常."""
        layout = bundle_install_layout(
            "demo",
            {
                "SKILL.md": "---\nname: demo\ndescription: d\n---\nBody\n",
                "reference.md": "ok content",
                "c:/evil.md": "evil content",
            },
        )
        # bundle 应是 directory 类型 (有 reference.md 这个 valid extra file)
        assert layout.kind == "directory", (
            f"bundle 应是 directory 类型, 实际: {layout.kind}"
        )
        # SKILL.md 仍 install
        assert "SKILL.md" in layout.directory_files
        assert "reference.md" in layout.directory_files
        # 盘符 key 排除
        assert "c:/evil.md" not in layout.directory_files, (
            f"盘符 key c:/evil.md 不应在 dir_files, "
            f"实际: {list(layout.directory_files.keys())}"
        )
        # 不应有 c: 这样的奇怪子目录
        for path in layout.directory_files:
            assert not path.startswith("c:"), (
                f"dir_files 不应有 c: 前缀路径, 实际含: {path}"
            )

    def test_absolute_posix_key_excluded_from_dir_files(self):
        """`/etc/passwd` 键不进 `dir_files`."""
        layout = bundle_install_layout(
            "demo",
            {
                "SKILL.md": "---\nname: demo\n---\nBody\n",
                "/etc/passwd": "should not install",
            },
        )
        # /etc/passwd 经 lstrip / 变成 "etc/passwd" — 当前可能通过
        # 修复后: 必须显式拒绝绝对路径键
        # 注意: 这里 "etc/passwd" 不是绝对路径, lstrip 已经处理.
        # 我们用真正的绝对路径测试 (不被 lstrip 影响):
        layout2 = bundle_install_layout(
            "demo2",
            {
                "SKILL.md": "---\nname: demo2\n---\nBody\n",
                "////etc/passwd": "deeply absolute",  # 多 slash, lstrip 后仍多 slash
            },
        )
        # 修复后: 这种 key 应该被识别为 absolute 并排除
        for path in layout2.directory_files:
            # 不应出现 etc/passwd 这种可能被解释为写 /etc 的路径
            # (虽然 POSIX 写到 <root>/<name>/etc/passwd 不出 root, 但语义有攻击意图)
            assert "etc/passwd" not in path, (
                f"绝对路径键 etc/passwd 应被排除, 实际含: {path}"
            )

    def test_dotdot_key_excluded_from_dir_files(self):
        """`../escape.md` 键不进 `dir_files` (旧行为, 不退化)."""
        layout = bundle_install_layout(
            "demo",
            {
                "SKILL.md": "---\nname: demo\n---\nBody\n",
                "../escape.md": "should not install",
            },
        )
        assert "../escape.md" not in layout.directory_files
        assert "escape.md" not in layout.directory_files, (
            f"../escape.md 解析后是 escape.md, 应被拒"
        )

    def test_mixed_safe_and_unsafe_keys(self):
        """混合安全 + 不安全 keys, 只有安全进 dir_files."""
        layout = bundle_install_layout(
            "demo",
            {
                "SKILL.md": "---\nname: demo\n---\nBody\n",
                "reference.md": "ok content",
                "sub/nested.md": "nested ok",
                "c:/evil.md": "bad 1",
                "Z:/escape.md": "bad 2",
                "/absolute.md": "bad 3",
                "../escape.md": "bad 4",
            },
        )
        assert "SKILL.md" in layout.directory_files
        assert "reference.md" in layout.directory_files
        assert "sub/nested.md" in layout.directory_files
        # 所有不安全 key 排除
        for bad in ("c:/evil.md", "Z:/escape.md", "/absolute.md", "../escape.md"):
            assert bad not in layout.directory_files, (
                f"不安全 key {bad} 应被排除, 实际 dir_files: {list(layout.directory_files)}"
            )
