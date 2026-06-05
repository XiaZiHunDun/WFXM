"""R2-18 [H] data_loss — corrupt skill_usage.json 永久丢失 analytics.

Audit (`docs/reviews/project-deep-audit-2026-06-r1to8.md` §R2-18):
``butler/skills/usage.py:24-30`` in ``UsageTracker._load``:

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load skill usage: %s", e)
                self._data = {}

问题:
- JSON 解析失败 → ``self._data = {}`` in-memory 清零
- 损坏文件**就地保留在原路径**,没有任何备份
- 后续 ``_save()`` 写回时覆盖原文件 → 原始 analytics **永久丢失**
- 操作者无法恢复或诊断损坏的 usage 数据

修复策略:
- 损坏时 rename ``<file>.corrupt-<unix_ts>`` (forensic 保留)
- 写入 diagnostics buffer (与 R2-8/9/11/12/13/14/15 一致)
- log at WARNING with ``exc_info``
- 然后 fresh start (``self._data = {}``)
- 合法 JSON / 缺文件 → 行为不变

行为保证:
1) 损坏 JSON → 原地文件被 rename 为 ``.corrupt-<ts>``
2) 损坏 JSON → ``self._data`` 是 ``{}`` (fresh start)
3) 损坏 JSON → log at WARNING with exc_info
4) 损坏 JSON → diagnostics buffer 记录事件 (供 /诊断 使用)
5) 合法 JSON → 不 rename, 正常 load
6) 缺文件 → fresh start, 不 rename
7) 损坏后 ``on_view`` / ``on_use`` 仍能正常工作 (行为连续性)
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import pytest

from butler.skills import usage as usage_mod
from butler.skills.usage import UsageTracker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_diagnostics():
    """Reset module-level diagnostics buffer around every test for isolation."""
    usage_mod.reset_usage_data_corruption()
    yield
    usage_mod.reset_usage_data_corruption()


# ---------------------------------------------------------------------------
# Test 1: corrupt file → renamed to .corrupt-<ts>
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCorruptFileRenamed:
    """损坏文件必须被 rename 为 ``.corrupt-<ts>`` (forensic 保留)."""

    def test_corrupt_file_is_renamed(self, tmp_path: Path):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("{this is not valid json", encoding="utf-8")

        UsageTracker(usage_file)

        # 原路径下不再有损坏文件
        assert not usage_file.exists(), (
            f"原路径下应已无损坏文件, 但仍存在: {usage_file}"
        )
        # 同目录下应有 .corrupt-<ts> 备份
        backups = list(tmp_path.glob("skill_usage.json.corrupt-*"))
        assert len(backups) == 1, (
            f"应有 1 个 .corrupt-<ts> 备份, 实际: {backups}"
        )
        # 备份内容与原损坏内容一致
        assert backups[0].read_text(encoding="utf-8") == "{this is not valid json"

    def test_corrupt_backup_name_includes_unix_ts(self, tmp_path: Path):
        """备份名应包含 timestamp (整型, 纳秒级避免同秒碰撞) 便于排序."""
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("not json", encoding="utf-8")

        UsageTracker(usage_file)

        backups = list(tmp_path.glob("skill_usage.json.corrupt-*"))
        assert len(backups) == 1
        m = re.match(r"skill_usage\.json\.corrupt-(\d+)$", backups[0].name)
        assert m, f"备份名格式应为 skill_usage.json.corrupt-<ts>, 实际: {backups[0].name}"
        # ts 应为正整数 (纳秒级时间戳, 远大于 10^15)
        ts = int(m.group(1))
        assert ts > 1_000_000_000_000, (
            f"corrupt ts 期望纳秒级 (>10^15), 实际: {ts}"
        )


# ---------------------------------------------------------------------------
# Test 2: corrupt file → fresh start (in-memory _data is empty)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCorruptFileFreshStart:
    """损坏文件 → in-memory fresh start, 不抛异常."""

    def test_in_memory_data_is_empty(self, tmp_path: Path):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("garbage", encoding="utf-8")

        tracker = UsageTracker(usage_file)

        assert tracker.get_all_stats() == {}, (
            "损坏文件应导致 fresh start (in-memory data is empty)"
        )

    def test_construction_does_not_raise(self, tmp_path: Path):
        """构造函数不能因为损坏文件而抛异常 (行为连续性)."""
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("definitely not json {{{", encoding="utf-8")

        # 必须不抛
        UsageTracker(usage_file)


# ---------------------------------------------------------------------------
# Test 3: corrupt file → log at WARNING with exc_info
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCorruptFileLogging:
    """损坏时 log at WARNING with exc_info (traceback 不丢)."""

    def test_logs_warning_with_exc_info(self, tmp_path: Path, caplog):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("not json", encoding="utf-8")

        with caplog.at_level(logging.DEBUG, logger="butler.skills.usage"):
            UsageTracker(usage_file)

        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING
        ]
        assert warning_records, (
            "损坏文件必须 log at WARNING, 实际 log 记录: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )
        # 必须含 exc_info (保留 traceback)
        assert any(r.exc_info is not None for r in warning_records), (
            "WARNING log 必须含 exc_info (保留 traceback), 实际: "
            f"{[(r.message, r.exc_info) for r in warning_records]}"
        )
        # 关键词让操作者知道是 skill usage 损坏
        assert any(
            "skill usage" in r.message.lower()
            for r in warning_records
        ), (
            f"WARNING log 应提及 'skill usage', 实际: "
            f"{[r.message for r in warning_records]}"
        )

    def test_logs_warning_on_oserror_too(self, tmp_path: Path, caplog, monkeypatch):
        """OSError (读权限等) 也必须 rename + log, 不只是 JSONDecodeError."""
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("{}", encoding="utf-8")  # valid content, but…

        # 强制 read_text 抛 OSError
        def _explode(*args, **kwargs):
            raise OSError("simulated read failure")

        monkeypatch.setattr(Path, "read_text", _explode)

        with caplog.at_level(logging.DEBUG, logger="butler.skills.usage"):
            UsageTracker(usage_file)

        warning_records = [
            r for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert warning_records
        assert any(r.exc_info is not None for r in warning_records)


# ---------------------------------------------------------------------------
# Test 4: corrupt file → diagnostics buffer records event
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCorruptFileDiagnostics:
    """损坏事件记入 diagnostics buffer (供 /诊断 聚合)."""

    def test_diagnostics_records_corruption(self, tmp_path: Path):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("garbage", encoding="utf-8")

        UsageTracker(usage_file)

        records = usage_mod.recent_usage_data_corruption()
        assert len(records) == 1
        rec = records[0]
        assert rec["kind"] == "skill_usage_corrupt"
        # 错误消息应该被记录 (Python 解析器具体措辞因内容而异,
        # contract 是 "记录了" 不是 "包含某关键词")
        assert rec["error"]
        assert rec["path"] == str(usage_file)
        # 备份路径应被记录
        assert rec["backup_path"]
        assert "corrupt-" in rec["backup_path"]
        # ts 应是 unix ts (整型)
        assert isinstance(rec["ts"], (int, float))
        assert rec["ts"] > 0

    def test_diagnostics_empty_initially(self):
        assert usage_mod.recent_usage_data_corruption() == []

    def test_reset_clears_buffer(self, tmp_path: Path):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("garbage", encoding="utf-8")
        UsageTracker(usage_file)
        assert usage_mod.recent_usage_data_corruption()

        usage_mod.reset_usage_data_corruption()
        assert usage_mod.recent_usage_data_corruption() == []

    def test_diagnostics_buffer_is_bounded(self, tmp_path: Path, monkeypatch):
        """buffer 满后按 FIFO 截断, 防止长会话无限增长."""
        monkeypatch.setattr(usage_mod, "_MAX_USAGE_CORRUPTION_ENTRIES", 3)
        for i in range(5):
            usage_file = tmp_path / f"u{i}.json"
            usage_file.write_text("not json", encoding="utf-8")
            UsageTracker(usage_file)
        records = usage_mod.recent_usage_data_corruption()
        assert len(records) == 3
        # FIFO: 最早 2 个 (u0, u1) 应被丢弃
        assert all(
            "u0.json" not in r["path"] and "u1.json" not in r["path"]
            for r in records
        ), f"最旧 2 个 entry 应被 FIFO 丢弃, 实际: {records!r}"


# ---------------------------------------------------------------------------
# Test 5: valid JSON → no rename, normal load
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidJson:
    """合法 JSON 不触发 rename / 损坏路径, 行为不变."""

    def test_valid_json_loads_normally(self, tmp_path: Path):
        usage_file = tmp_path / "skill_usage.json"
        valid_data = {
            "skill-a": {"creates": 1, "views": 2, "uses": 3, "deletes": 0, "merges_in": 0},
        }
        usage_file.write_text(json.dumps(valid_data), encoding="utf-8")

        tracker = UsageTracker(usage_file)

        # 数据被正常加载
        assert tracker.get_all_stats() == valid_data
        # 没有触发 rename (没有 .corrupt-* 文件)
        backups = list(tmp_path.glob("skill_usage.json.corrupt-*"))
        assert backups == []
        # diagnostics buffer 是空 (没有损坏事件)
        assert usage_mod.recent_usage_data_corruption() == []


# ---------------------------------------------------------------------------
# Test 6: missing file → fresh start, no rename
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMissingFile:
    """缺文件时 fresh start, 不 rename (rename 是损坏专属)."""

    def test_missing_file_fresh_start(self, tmp_path: Path):
        usage_file = tmp_path / "does_not_exist.json"
        assert not usage_file.exists()

        tracker = UsageTracker(usage_file)

        assert tracker.get_all_stats() == {}
        # 不应创建任何 .corrupt-* 文件
        backups = list(tmp_path.glob("*.corrupt-*"))
        assert backups == []
        # 不写 diagnostics (没有损坏事件, 只是没有文件)
        assert usage_mod.recent_usage_data_corruption() == []


# ---------------------------------------------------------------------------
# Test 7: behavior preserved after corruption
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBehaviorAfterCorruption:
    """损坏后 on_view / on_use / on_create 仍能正常工作 (连续性)."""

    def test_on_view_after_corruption_writes_new_file(self, tmp_path: Path):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("not json", encoding="utf-8")

        tracker = UsageTracker(usage_file)
        tracker.on_view("skill-x")

        # on_view 应创建新文件 (因为损坏文件已 rename)
        assert usage_file.exists()
        data = json.loads(usage_file.read_text(encoding="utf-8"))
        assert "skill-x" in data
        assert data["skill-x"]["views"] == 1

    def test_on_use_after_corruption_works(self, tmp_path: Path):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("garbage", encoding="utf-8")

        tracker = UsageTracker(usage_file)
        tracker.on_use("skill-y")

        data = json.loads(usage_file.read_text(encoding="utf-8"))
        assert "skill-y" in data
        assert data["skill-y"]["uses"] == 1

    def test_corrupt_file_not_overwritten_directly(self, tmp_path: Path):
        """损坏文件不应被原位覆盖 (它应先被 rename).

        这个测试通过以下方式间接验证: UsageTracker 构造后, 原路径下
        是新文件 (后续 on_view 写出来的), 而不是损坏的旧内容.
        """
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("CORRUPT", encoding="utf-8")

        UsageTracker(usage_file)
        # 此时原路径下无文件 (已 rename)
        assert not usage_file.exists()

        # 后续 on_view 写到原路径, 应是新内容
        UsageTracker(usage_file).on_view("skill-z")
        assert usage_file.exists()
        content = usage_file.read_text(encoding="utf-8")
        assert "CORRUPT" not in content
        assert "skill-z" in content


# ---------------------------------------------------------------------------
# Test 8: rename 失败时, _save() 必须被 block (避免 R2-18 数据丢失重现)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenameFailedBlocksSave:
    """当 corrupt 文件 rename 失败时, _save() 必须被 block.

    防止 on_view/on_use 后续写入覆盖原损坏文件, 重新制造 R2-18 数据丢失.
    """

    def test_save_blocked_when_rename_fails(self, tmp_path: Path, monkeypatch):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("not json", encoding="utf-8")

        # 强制 os.replace 抛 OSError
        def _explode(*args, **kwargs):
            raise OSError("simulated cross-device rename failure")

        monkeypatch.setattr(os, "replace", _explode)

        tracker = UsageTracker(usage_file)

        # 原损坏文件应仍在原路径 (rename 失败)
        assert usage_file.exists()
        assert usage_file.read_text(encoding="utf-8") == "not json"

        # _save() 必须不覆盖损坏文件
        tracker.on_view("skill-blocked")

        # 文件内容仍然是损坏的 (未被 _save 覆盖)
        assert usage_file.read_text(encoding="utf-8") == "not json"

    def test_logs_error_when_rename_fails(self, tmp_path: Path, monkeypatch, caplog):
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("not json", encoding="utf-8")

        def _explode(*args, **kwargs):
            raise OSError("simulated")

        monkeypatch.setattr(os, "replace", _explode)

        with caplog.at_level(logging.DEBUG, logger="butler.skills.usage"):
            UsageTracker(usage_file)

        error_records = [
            r for r in caplog.records if r.levelno >= logging.ERROR
        ]
        assert error_records, (
            f"rename 失败必须 log at ERROR (不是 WARNING), 实际: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )
        # 必须含 exc_info
        assert any(r.exc_info is not None for r in error_records)

    def test_save_block_logs_warning(self, tmp_path: Path, monkeypatch, caplog):
        """_save() 被 block 时, 应 log at WARNING 说明跳过原因."""
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("not json", encoding="utf-8")

        def _explode(*args, **kwargs):
            raise OSError("simulated")

        monkeypatch.setattr(os, "replace", _explode)

        tracker = UsageTracker(usage_file)

        with caplog.at_level(logging.DEBUG, logger="butler.skills.usage"):
            tracker.on_view("skill-x")

        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and "skipped" in r.message.lower()
        ]
        assert warning_records, (
            f"_save() block 必须 log WARNING with 'skipped', 实际: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )

    def test_diagnostics_records_rename_failure(self, tmp_path: Path, monkeypatch):
        """rename 失败时, diagnostics 仍应记录事件 (操作者可查)."""
        usage_file = tmp_path / "skill_usage.json"
        usage_file.write_text("not json", encoding="utf-8")

        def _explode(*args, **kwargs):
            raise OSError("simulated")

        monkeypatch.setattr(os, "replace", _explode)

        UsageTracker(usage_file)

        records = usage_mod.recent_usage_data_corruption()
        assert len(records) == 1
        assert records[0]["kind"] == "skill_usage_corrupt"
