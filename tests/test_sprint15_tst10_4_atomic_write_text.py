"""Sprint 15 TST-10-4: butler.io.atomic_write.atomic_write_text 直测.

atomic_write_text 是 REL-3 的核心增强（fsync + symlink 拒绝）。
之前 0 个直测，仅通过 atomic_json_write/_write_entry/_save_all 间接覆盖。
此文件补齐对该函数的直接行为测试。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ── 基础写行为 ─────────────────────────────────────────────


class TestBasicWrite:
    def test_writes_content_to_new_file(self, tmp_path: Path):
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "data.txt"
        atomic_write_text(target, "hello world")

        assert target.is_file()
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_creates_parent_dirs(self, tmp_path: Path):
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "deep" / "nested" / "dirs" / "file.txt"
        atomic_write_text(target, "ok")

        assert target.is_file()
        assert target.read_text(encoding="utf-8") == "ok"

    def test_overwrites_existing_file(self, tmp_path: Path):
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "file.txt"
        target.write_text("OLD", encoding="utf-8")

        atomic_write_text(target, "NEW")

        assert target.read_text(encoding="utf-8") == "NEW"

    def test_preserves_unicode(self, tmp_path: Path):
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "cn.txt"
        atomic_write_text(target, "测试 中文 🚀")

        text = target.read_text(encoding="utf-8")
        assert text == "测试 中文 🚀"

    def test_handles_empty_string(self, tmp_path: Path):
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "empty.txt"
        atomic_write_text(target, "")

        assert target.is_file()
        assert target.read_text(encoding="utf-8") == ""

    def test_no_tmp_file_residue_on_success(self, tmp_path: Path):
        """成功写后不应留下 .tmp 残留。"""
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "data.json"
        atomic_write_text(target, "x")

        assert not (tmp_path / "data.json.tmp").exists()

    def test_custom_encoding(self, tmp_path: Path):
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "latin.txt"
        atomic_write_text(target, "café", encoding="latin-1")

        # 文件可按指定编码读回
        assert target.read_text(encoding="latin-1") == "café"


# ── 文件权限 ────────────────────────────────────────────────


class TestFilePermissions:
    def test_writes_with_0o600_permissions(self, tmp_path: Path):
        """文件应以 0o600 创建（owner 读写，其他人无权限）。"""
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "secret.txt"
        atomic_write_text(target, "private")

        mode = target.stat().st_mode & 0o777
        assert mode == 0o600, f"期望 0o600，实际 {oct(mode)}"


# ── symlink 拒绝 ──────────────────────────────────────────────


class TestSymlinkRejection:
    def test_rejects_symlink_target(self, tmp_path: Path):
        """当目标已是 symlink 时，atomic_write_text 应拒绝。"""
        from butler.io.atomic_write import atomic_write_text

        real_dir = tmp_path / "real"
        real_dir.mkdir()
        real_file = real_dir / "data.json"
        real_file.write_text("real", encoding="utf-8")

        link_path = tmp_path / "link.json"
        link_path.symlink_to(real_file)

        with pytest.raises(OSError, match="[Ss]ymlink"):
            atomic_write_text(link_path, "injected")

        # 真实文件不应被覆盖
        assert real_file.read_text(encoding="utf-8") == "real"

    def test_final_target_not_symlink_after_resolve_is_allowed(self, tmp_path: Path):
        """文档化安全边界：当前实现只检测 final target 是否 symlink，
        不会检测祖先目录是否为 symlink。父目录为 symlink 时，最终 target
        仍解析到真实文件，因此会被允许写入。

        提升为完整防御需另开 audit fix（中间路径全链 symlink 检测）。"""
        from butler.io.atomic_write import atomic_write_text

        real_parent = tmp_path / "real_parent"
        real_parent.mkdir()
        real_file = real_parent / "data.json"
        real_file.write_text("original", encoding="utf-8")

        # link_parent -> real_parent
        link_parent = tmp_path / "link_parent"
        link_parent.symlink_to(real_parent)

        target = link_parent / "data.json"
        # 当前实现：父 symlink 不会被检测 → 写入成功（覆盖目标文件）
        atomic_write_text(target, "injected")

        # 真实文件被覆盖（已知行为）
        assert real_file.read_text(encoding="utf-8") == "injected"


# ── fsync 行为 ──────────────────────────────────────────────


class TestFsyncInvoked:
    def test_fsync_called_on_tmp(self, tmp_path: Path):
        """成功写应触发 fsync（确保进程崩溃后内容不丢）。"""
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "fsync.txt"
        real_fsync = os.fsync
        fsync_calls: list[int] = []

        def counting_fsync(fd: int) -> None:
            fsync_calls.append(fd)
            return real_fsync(fd)

        with patch("os.fsync", counting_fsync):
            atomic_write_text(target, "data")

        # 至少调用了 1 次（对 tmp 文件）
        assert len(fsync_calls) >= 1, "fsync 应至少被调用 1 次"


# ── tmp 命名与清理 ──────────────────────────────────────────


class TestTmpFileNaming:
    def test_uses_suffix_dot_tmp(self, tmp_path: Path):
        """tmp 文件应命名为 <target>.tmp。"""
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "data.json"
        # 监控 os.open 验证 tmp 路径命名
        opened_paths: list[str] = []
        real_open = os.open

        def capturing_open(path, *args, **kwargs):
            opened_paths.append(str(path))
            return real_open(path, *args, **kwargs)

        with patch("os.open", capturing_open):
            atomic_write_text(target, "x")

        # 至少有一次打开 .tmp 文件
        assert any(p.endswith(".json.tmp") for p in opened_paths), (
            f"期望找到 .json.tmp，实际打开：{opened_paths}"
        )

    def test_uses_o_nofollow_flag(self, tmp_path: Path):
        """os.open 应使用 O_NOFOLLOW（防 symlink 跟随）。"""
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "nofollow.txt"
        seen_flags: list[int] = []
        real_open = os.open

        def capturing_open(path, flags, *args, **kwargs):
            seen_flags.append(flags)
            return real_open(path, flags, *args, **kwargs)

        with patch("os.open", capturing_open):
            atomic_write_text(target, "x")

        # O_NOFOLLOW 标志位
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        assert any((f & nofollow) for f in seen_flags), (
            f"期望 O_NOFOLLOW 标志位，实际 flags={seen_flags}"
        )

    def test_uses_o_creat_and_o_trunc(self, tmp_path: Path):
        """os.open 应使用 O_CREAT + O_TRUNC（每次写都覆盖）。"""
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "create_trunc.txt"
        seen_flags: list[int] = []
        real_open = os.open

        def capturing_open(path, flags, *args, **kwargs):
            seen_flags.append(flags)
            return real_open(path, flags, *args, **kwargs)

        with patch("os.open", capturing_open):
            atomic_write_text(target, "x")

        # 至少一次同时含 O_CREAT + O_WRONLY + O_TRUNC
        assert any(
            (f & os.O_CREAT) and (f & os.O_WRONLY) and (f & os.O_TRUNC)
            for f in seen_flags
        ), f"期望 O_CREAT|O_WRONLY|O_TRUNC，实际 flags={seen_flags}"


# ── 边界情况 ──────────────────────────────────────────────


class TestEdgeCases:
    def test_existing_file_with_old_content_replaced(self, tmp_path: Path):
        """已存在且大于新内容长度的文件应被截断。"""
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "trunc.txt"
        target.write_text("x" * 1000, encoding="utf-8")
        assert len(target.read_text(encoding="utf-8")) == 1000

        atomic_write_text(target, "short")

        assert target.read_text(encoding="utf-8") == "short"

    def test_path_string_coerced_to_path(self, tmp_path: Path):
        """str 路径应被接受（不强制要求 Path 对象）。"""
        from butler.io.atomic_write import atomic_write_text

        target_str = str(tmp_path / "string_path.txt")
        atomic_write_text(target_str, "ok")  # type: ignore[arg-type]

        assert Path(target_str).read_text(encoding="utf-8") == "ok"

    def test_idempotent_overwrite(self, tmp_path: Path):
        """重复写相同内容应稳定（无残留 tmp）。"""
        from butler.io.atomic_write import atomic_write_text

        target = tmp_path / "idem.txt"
        for _ in range(5):
            atomic_write_text(target, "stable")

        assert target.read_text(encoding="utf-8") == "stable"
        # 不应有任何 .tmp 残留
        assert not (tmp_path / "idem.txt.tmp").exists()
