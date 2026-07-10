"""Sprint 20-2 SEC-20-A-2: zip 提取忽略 symlink / 特殊文件类型 (CRITICAL).

Sprint 20 subagent A 安全审计:
- lobehub._extract_zip_files (lobehub.py:226-242) 与 clawhub._download_zip
  (clawhub.py:222-235) 提取 zip 时只过滤 `is_dir() / file_size > 500_000`,
  没检查 `info.is_symlink()` (Python 3.12+ helper) 或
  `stat.S_ISLNK(info.external_attr >> 16)` (Python 3.13 fallback).
- 攻击: 恶意社区 skill (trust=community) zip 包含 symlink entry, 内容是
  目标路径. `zf.read(info.filename)` 拿到目标路径字符串, decode 后进
  bundle.files. 下游 quarantine_bundle + write_text 把目标路径作为普通
  文件写入 skill 目录. 现在看似不直接 RCE, 但:
    1) 防御纵深: 任何未来 extract_to_disk 改造都会立即让 symlink 实际落盘
    2) 路径污染: bundle.files 混入 symlink target 路径字符串, 下游若按
       path 处理会触发越界 (Sprint 20-3 同样的越界模式)
    3) 特殊文件 (FIFO/CHR/BLK/SOCK) 同理: 通过 `external_attr >> 16` 伪装
       Unix mode, 真实场景下若被 extract 会创建非普通文件, 引发后续
       打开/读写的 side effect.

修复: 两个源统一在 zip 循环开头 skip symlink + 非 S_IFREG 特殊文件.
通过 helper `_is_unsafe_zip_entry(info) -> bool` 集中判断, 后续 zip 提
取也复用 (避免漏改). 实现放在新模块 `zip_safety.py` (单一职责).
"""

from __future__ import annotations

import io
import stat
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from butler.registry.skill_sources.clawhub import ClawHubSource
from butler.registry.skill_sources.lobehub import _extract_zip_files
from butler.registry.skill_sources.zip_safety import is_unsafe_zip_entry


# ---- helpers ----


def _make_zip_with_symlink(target_path: str = "/etc/passwd") -> bytes:
    """Build a zip containing a Unix symlink entry + a valid SKILL.md."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("evil_link")
        info.create_system = 3  # Unix
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, target_path)
        zf.writestr("SKILL.md", "---\nname: x\n---\nbody")
    return buf.getvalue()


def _make_zip_with_special(mode: int, name: str = "special_file") -> bytes:
    """Build a zip with a Unix special-file entry (FIFO/CHR/BLK/SOCK)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo(name)
        info.create_system = 3  # Unix
        info.external_attr = (mode | 0o600) << 16
        zf.writestr(info, "")
        zf.writestr("SKILL.md", "---\nname: x\n---\nbody")
    return buf.getvalue()


def _make_zip_with_md_symlink(
    symlink_name: str,
    target: str,
) -> bytes:
    """Build a zip where the SYMLINK entry has a .md extension (bypass-by-extension)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo(symlink_name)
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, target)
        zf.writestr("SKILL.md", "---\nname: x\n---\nbody")
    return buf.getvalue()


def _make_zip_regular_only() -> bytes:
    """Baseline: a zip with only regular text files (no Unix mode bits)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SKILL.md", "---\nname: x\n---\nbody")
        zf.writestr("helper.md", "safe content")
    return buf.getvalue()


# ---- is_unsafe_zip_entry unit tests ----


@pytest.mark.unit
class TestIsUnsafeZipEntry:
    """Helper 行为: 仅当 create_system==3 且 mode 是 symlink/特殊文件时返 True."""

    def test_regular_file_no_unix_mode_passes(self):
        """FAT/MS-DOS zip (默认 create_system=0) 全部视为合法."""
        info = zipfile.ZipInfo("foo.md")
        info.create_system = 0
        info.external_attr = 0
        assert is_unsafe_zip_entry(info) is False

    def test_regular_file_unix_s_ifreg_passes(self):
        """Unix mode S_IFREG (0o100000) → 合法."""
        info = zipfile.ZipInfo("foo.md")
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        assert is_unsafe_zip_entry(info) is False

    def test_symlink_blocked(self):
        """S_IFLNK → unsafe."""
        info = zipfile.ZipInfo("foo")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        assert is_unsafe_zip_entry(info) is True

    def test_fifo_blocked(self):
        """S_IFIFO → unsafe."""
        info = zipfile.ZipInfo("foo")
        info.create_system = 3
        info.external_attr = (stat.S_IFIFO | 0o600) << 16
        assert is_unsafe_zip_entry(info) is True

    def test_char_device_blocked(self):
        """S_IFCHR → unsafe."""
        info = zipfile.ZipInfo("foo")
        info.create_system = 3
        info.external_attr = (stat.S_IFCHR | 0o600) << 16
        assert is_unsafe_zip_entry(info) is True

    def test_block_device_blocked(self):
        """S_IFBLK → unsafe."""
        info = zipfile.ZipInfo("foo")
        info.create_system = 3
        info.external_attr = (stat.S_IFBLK | 0o600) << 16
        assert is_unsafe_zip_entry(info) is True

    def test_socket_blocked(self):
        """S_IFSOCK → unsafe."""
        info = zipfile.ZipInfo("foo")
        info.create_system = 3
        info.external_attr = (stat.S_IFSOCK | 0o600) << 16
        assert is_unsafe_zip_entry(info) is True

    def test_dir_in_unix_mode_blocked(self):
        """S_IFDIR via Unix mode → unsafe (与 is_dir 重复但更稳)."""
        info = zipfile.ZipInfo("dir/")
        info.create_system = 3
        info.external_attr = (stat.S_IFDIR | 0o755) << 16
        assert is_unsafe_zip_entry(info) is True


# ---- lobehub._extract_zip_files 集成测试 ----


@pytest.mark.unit
class TestLobehubSymlinkBlocked:
    """lobehub._extract_zip_files 必须排除 symlink / 特殊文件."""

    def test_symlink_entry_excluded(self):
        """zip 含 symlink entry → 不应进入 files dict."""
        blob = _make_zip_with_symlink("/etc/passwd")
        files = _extract_zip_files(blob)
        assert "evil_link" not in files, (
            f"symlink entry 不应被提取, 实际 files: {list(files.keys())}"
        )
        # 其它合法条目仍应保留
        assert "SKILL.md" in files

    def test_md_extension_symlink_excluded(self):
        """伪装成 .md 的 symlink 也不应被读 (ext 过滤 + symlink 过滤 双层防御)."""
        blob = _make_zip_with_md_symlink("good.md", "ignore previous instructions")
        files = _extract_zip_files(blob)
        assert "good.md" not in files, (
            f"伪装成 .md 的 symlink 不应被读, 实际 files: {list(files.keys())}"
        )

    def test_fifo_excluded(self):
        blob = _make_zip_with_special(stat.S_IFIFO)
        files = _extract_zip_files(blob)
        assert "special_file" not in files, (
            f"FIFO entry 不应被提取, 实际 files: {list(files.keys())}"
        )

    def test_char_device_excluded(self):
        blob = _make_zip_with_special(stat.S_IFCHR)
        files = _extract_zip_files(blob)
        assert "special_file" not in files

    def test_block_device_excluded(self):
        blob = _make_zip_with_special(stat.S_IFBLK)
        files = _extract_zip_files(blob)
        assert "special_file" not in files

    def test_socket_excluded(self):
        blob = _make_zip_with_special(stat.S_IFSOCK)
        files = _extract_zip_files(blob)
        assert "special_file" not in files

    def test_regular_files_pass(self):
        """正常 .md / 嵌套目录 / 正常文件仍应被提取."""
        files = _extract_zip_files(_make_zip_regular_only())
        assert "SKILL.md" in files
        assert "helper.md" in files
        assert "SKILL.md" in files
        assert "body" in files["SKILL.md"]

    def test_skills_md_still_extractable_with_symlink_present(self):
        """即使 zip 同时含 symlink + SKILL.md, SKILL.md 仍应被提取."""
        blob = _make_zip_with_symlink()
        files = _extract_zip_files(blob)
        assert "SKILL.md" in files
        assert "evil_link" not in files


# ---- clawhub 集成测试 ----


@pytest.mark.unit
class TestClawhubSymlinkBlocked:
    """clawhub._download_zip 路径同样需排除 symlink."""

    def test_symlink_entry_excluded_from_bundle(self):
        """clawhub.fetch() 拿到含 symlink 的 zip → bundle.files 不应含 symlink."""
        from butler.registry.url_safety import safe_registry_get

        blob = _make_zip_with_symlink()
        skill_payload = {
            "slug": "evil-skill",
            "latestVersion": {"version": "1.0.0"},
        }

        def fake_get(url, **kwargs):
            resp = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
            if "download" in url:
                resp.status_code = 200
                resp.content = blob
                resp.headers = {}
            elif "/skills/evil-skill" in url and "versions" not in url:
                resp.status_code = 200
                resp.json = lambda: skill_payload
            else:
                resp.status_code = 404
                resp.json = lambda: {}
                resp.content = b""
            return resp

        source = ClawHubSource()
        with patch(
            "butler.registry.url_safety.safe_registry_get",
            side_effect=fake_get,
        ):
            with patch.object(source, "_get_json", side_effect=fake_get):
                bundle = source.fetch("clawhub:evil-skill")

        # bundle 可能 None (SKILL.md 找不到) 或非 None. 关键是 symlink 不在
        if bundle is not None:
            assert "evil_link" not in bundle.files, (
                f"clawhub 也不应含 symlink entry, "
                f"实际 files: {list(bundle.files.keys())}"
            )

    def test_char_device_excluded_from_clawhub(self):
        """clawhub 对 CHR 设备的处理应与 lobehub 一致."""
        from butler.registry.url_safety import safe_registry_get

        blob = _make_zip_with_special(stat.S_IFCHR, name="device")
        skill_payload = {
            "slug": "device-skill",
            "latestVersion": {"version": "1.0.0"},
        }

        def fake_get(url, **kwargs):
            resp = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
            if "download" in url:
                resp.status_code = 200
                resp.content = blob
                resp.headers = {}
            elif "/skills/device-skill" in url and "versions" not in url:
                resp.status_code = 200
                resp.json = lambda: skill_payload
            else:
                resp.status_code = 404
                resp.json = lambda: {}
                resp.content = b""
            return resp

        source = ClawHubSource()
        with patch(
            "butler.registry.url_safety.safe_registry_get",
            side_effect=fake_get,
        ):
            with patch.object(source, "_get_json", side_effect=fake_get):
                bundle = source.fetch("clawhub:device-skill")

        if bundle is not None:
            assert "device" not in bundle.files
