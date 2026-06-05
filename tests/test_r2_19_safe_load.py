"""R2-19 [H] bad_fallback — 12+ 状态文件统一反模式.

Audit (`docs/reviews/project-deep-audit-2026-06-r1to8.md` §R2-19):
12+ state files (permissions/approvals.py, mcp/config.py, runtime/loader.py,
runtime/audit.py, runtime/task_store.py 等) 全部用同一反模式:

    try:
        data = json.loads(path.read_text(...))
    except (OSError, json.JSONDecodeError):
        return default  # ← silent_drop: 用户无感, 数据永久丢失

最危险: ``permissions/approvals.py:62-69`` 损坏时静默丢弃所有
"always allow", 用户看到 **大量重提示** 或以为"批准被遗忘".

修复: 抽 ``butler/io/safe_load.py`` 统一 helper:
* safe_load_json / safe_load_yaml
* 损坏时 rename .corrupt-<ns_ts> 备份 (forensic)
* log at WARNING with exc_info
* 记入模块级 diagnostics buffer (FIFO 50, 供 /诊断 聚合)
* 缺文件 / OSError 与损坏路径分流

行为保证 (per contract):
1) 缺文件 → default, 无 log, 无 record
2) 合法 JSON → 解析后数据
3) 合法 YAML → 解析后数据
4) 损坏 JSON → rename .corrupt-<ns_ts>, WARNING + exc_info, diagnostics, default
5) 损坏 YAML → 同上
6) OSError 读 → WARNING + exc_info, diagnostics (无 backup, 无 rename)
7) 解析结果为 None → default
8) diagnostics buffer FIFO 50
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from butler.io import safe_load as safe_load_mod
from butler.io.safe_load import (
    recent_state_file_corruption,
    reset_state_file_corruption,
    safe_load_json,
    safe_load_yaml,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_diagnostics():
    """Reset module-level diagnostics buffer around every test for isolation."""
    safe_load_mod.reset_state_file_corruption()
    yield
    safe_load_mod.reset_state_file_corruption()


# ---------------------------------------------------------------------------
# Test 1: missing file → default (no log, no record)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMissingFile:
    """缺文件 → default, 静默返回 (不是损坏)."""

    def test_missing_json_returns_default(self, tmp_path: Path):
        path = tmp_path / "does_not_exist.json"
        result = safe_load_json(
            path, default={"x": 1}, kind="test_kind",
        )
        assert result == {"x": 1}, "缺文件应返回 default"
        assert recent_state_file_corruption() == [], (
            "缺文件不应记入 diagnostics (不是损坏事件)"
        )

    def test_missing_yaml_returns_default(self, tmp_path: Path):
        path = tmp_path / "does_not_exist.yaml"
        result = safe_load_yaml(path, default=[], kind="test_kind")
        assert result == []
        assert recent_state_file_corruption() == []

    def test_missing_file_no_log(self, tmp_path: Path, caplog):
        path = tmp_path / "absent.json"
        with caplog.at_level(logging.DEBUG, logger="butler.io.safe_load"):
            safe_load_json(path, default={}, kind="test_kind")
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records == [], (
            f"缺文件不应 log WARNING, 实际: "
            f"{[(r.levelname, r.message) for r in warning_records]}"
        )


# ---------------------------------------------------------------------------
# Test 2: valid JSON / YAML → parsed data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidParsing:
    """合法 JSON / YAML → 正常解析, 无 rename."""

    def test_valid_json_loaded(self, tmp_path: Path):
        path = tmp_path / "ok.json"
        path.write_text(json.dumps({"a": 1, "b": [2, 3]}), encoding="utf-8")
        result = safe_load_json(path, default={}, kind="test_kind")
        assert result == {"a": 1, "b": [2, 3]}

    def test_valid_yaml_loaded(self, tmp_path: Path):
        path = tmp_path / "ok.yaml"
        path.write_text(yaml.safe_dump({"servers": {"x": 1}}), encoding="utf-8")
        result = safe_load_yaml(path, default={}, kind="test_kind")
        assert result == {"servers": {"x": 1}}

    def test_valid_json_no_rename(self, tmp_path: Path):
        path = tmp_path / "ok.json"
        path.write_text("{}", encoding="utf-8")
        safe_load_json(path, default={}, kind="test_kind")
        assert path.exists(), "合法文件不应被 rename"
        assert list(tmp_path.glob("*.corrupt-*")) == []

    def test_valid_yaml_no_rename(self, tmp_path: Path):
        path = tmp_path / "ok.yaml"
        path.write_text("a: 1", encoding="utf-8")
        safe_load_yaml(path, default={}, kind="test_kind")
        assert path.exists()
        assert list(tmp_path.glob("*.corrupt-*")) == []

    def test_valid_json_no_diagnostics(self, tmp_path: Path):
        path = tmp_path / "ok.json"
        path.write_text("{}", encoding="utf-8")
        safe_load_json(path, default={}, kind="test_kind")
        assert recent_state_file_corruption() == []


# ---------------------------------------------------------------------------
# Test 3: corrupt JSON / YAML → rename, log, record, default
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCorruptFile:
    """损坏文件 → rename + log + record + default."""

    def test_corrupt_json_renamed(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")

        result = safe_load_json(path, default={"d": 1}, kind="my_kind")

        assert result == {"d": 1}, "损坏 JSON 应返回 default"
        assert not path.exists(), "原路径下损坏文件应已被 rename"
        backups = list(tmp_path.glob("bad.json.corrupt-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "{not valid json"

    def test_corrupt_yaml_renamed(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("foo: [unclosed", encoding="utf-8")

        result = safe_load_yaml(path, default={"d": 1}, kind="my_kind")

        assert result == {"d": 1}
        assert not path.exists()
        backups = list(tmp_path.glob("bad.yaml.corrupt-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "foo: [unclosed"

    def test_corrupt_json_logs_warning_with_exc_info(self, tmp_path: Path, caplog):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")

        with caplog.at_level(logging.DEBUG, logger="butler.io.safe_load"):
            safe_load_json(path, default={}, kind="approvals")

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records, "损坏 JSON 必须 log WARNING"
        assert any(r.exc_info is not None for r in warning_records), (
            "WARNING log 必须含 exc_info (保留 traceback)"
        )
        # log 应含 kind 让操作者知道是哪个 state file 坏了
        assert any(
            "approvals" in r.message for r in warning_records
        ), f"WARNING log 应含 'approvals' (kind), 实际: {[r.message for r in warning_records]}"

    def test_corrupt_yaml_logs_warning(self, tmp_path: Path, caplog):
        path = tmp_path / "bad.yaml"
        path.write_text("not: valid: yaml: [", encoding="utf-8")

        with caplog.at_level(logging.DEBUG, logger="butler.io.safe_load"):
            safe_load_yaml(path, default={}, kind="my_yaml")

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records
        assert any(r.exc_info is not None for r in warning_records)
        assert any("my_yaml" in r.message for r in warning_records)

    def test_corrupt_json_records_diagnostics(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")

        safe_load_json(path, default={}, kind="approvals")

        records = recent_state_file_corruption()
        assert len(records) == 1
        rec = records[0]
        assert rec["kind"] == "approvals"
        assert rec["path"] == str(path)
        assert rec["error"]
        assert rec["backup_path"]
        assert "corrupt-" in rec["backup_path"]

    def test_corrupt_yaml_records_diagnostics(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("foo: [unclosed", encoding="utf-8")

        safe_load_yaml(path, default={}, kind="mcp_config")

        records = recent_state_file_corruption()
        assert len(records) == 1
        assert records[0]["kind"] == "mcp_config"


# ---------------------------------------------------------------------------
# Test 4: OSError reading → log, no rename
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOSErrorReading:
    """OSError 读文件 → log + record (不 rename, 因为无法证明文件值得保留)."""

    def test_oserror_logs_warning(self, tmp_path: Path, caplog, monkeypatch):
        path = tmp_path / "perm.json"
        path.write_text("{}", encoding="utf-8")

        def _explode(*args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "read_text", _explode)

        with caplog.at_level(logging.DEBUG, logger="butler.io.safe_load"):
            result = safe_load_json(path, default={"d": 1}, kind="my_kind")

        assert result == {"d": 1}, "OSError 应返回 default"
        # 文件仍在 (没 rename, 也没法 rename — read 已失败)
        assert path.exists()
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_records
        assert any(r.exc_info is not None for r in warning_records)

    def test_oserror_records_no_backup(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "perm.json"
        path.write_text("{}", encoding="utf-8")

        def _explode(*args, **kwargs):
            raise OSError("perm")

        monkeypatch.setattr(Path, "read_text", _explode)

        safe_load_json(path, default={}, kind="my_kind")

        records = recent_state_file_corruption()
        assert len(records) == 1
        # OSError 分支: backup_path 应为 None (没 rename)
        assert records[0]["backup_path"] is None
        # 没有 .corrupt-* 文件被创建
        assert list(tmp_path.glob("*.corrupt-*")) == []


# ---------------------------------------------------------------------------
# Test 5: parsed result is None → default
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNoneParseResult:
    """合法但解析为 None (e.g. 空 JSON / 'null') → default."""

    def test_empty_json_returns_default(self, tmp_path: Path):
        path = tmp_path / "empty.json"
        path.write_text("", encoding="utf-8")
        result = safe_load_json(path, default={"d": 1}, kind="my_kind")
        # 空字符串触发 JSONDecodeError, 不是 None
        # 这里我们用 'null' 触发 None
        path.write_text("null", encoding="utf-8")
        result = safe_load_json(path, default={"d": 1}, kind="my_kind")
        assert result == {"d": 1}, "json 'null' 解析为 None, 应返回 default"

    def test_yaml_null_returns_default(self, tmp_path: Path):
        path = tmp_path / "null.yaml"
        path.write_text("~", encoding="utf-8")  # YAML null
        result = safe_load_yaml(path, default={"d": 1}, kind="my_kind")
        assert result == {"d": 1}, "YAML '~' 解析为 None, 应返回 default"


# ---------------------------------------------------------------------------
# Test 6: diagnostics buffer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDiagnosticsBuffer:
    """diagnostics buffer 行为 (FIFO 50, reset, 公共 reader)."""

    def test_reader_empty_initially(self):
        assert recent_state_file_corruption() == []

    def test_reset_clears_buffer(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        safe_load_json(path, default={}, kind="k")
        assert recent_state_file_corruption()

        reset_state_file_corruption()
        assert recent_state_file_corruption() == []

    def test_buffer_is_bounded(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(safe_load_mod, "_MAX_STATE_CORRUPTION_ENTRIES", 3)
        for i in range(5):
            path = tmp_path / f"f{i}.json"
            path.write_text("not json", encoding="utf-8")
            safe_load_json(path, default={}, kind="k")
        records = recent_state_file_corruption()
        assert len(records) == 3
        # FIFO: 最早 2 个 (f0, f1) 应被丢弃
        assert all(
            "f0.json" not in r["path"] and "f1.json" not in r["path"]
            for r in records
        ), f"最旧 2 个 entry 应被 FIFO 丢弃, 实际: {records!r}"

    def test_kind_field_is_preserved(self, tmp_path: Path):
        """不同 state file 应能通过 kind 字段区分 (供 /诊断 显示)."""
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        safe_load_json(path, default={}, kind="permissions_approvals")

        records = recent_state_file_corruption()
        assert records[0]["kind"] == "permissions_approvals"


# ---------------------------------------------------------------------------
# Test 7: rename-failed 分支 (corrupt file + os.replace 失败)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenameFailedBranch:
    """corrupt 文件 + rename 失败时: 仍 log + record, backup_path=None."""

    def test_rename_failure_does_not_block_default(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")

        def _explode(*args, **kwargs):
            raise OSError("simulated rename failure")

        monkeypatch.setattr("os.replace", _explode)

        # 必须仍返回 default, 不抛
        result = safe_load_json(path, default={"d": 1}, kind="my_kind")
        assert result == {"d": 1}

    def test_rename_failure_records_no_backup(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")

        monkeypatch.setattr("os.replace", lambda *a, **kw: (_ for _ in ()).throw(OSError("simulated")))

        safe_load_json(path, default={}, kind="my_kind")

        records = recent_state_file_corruption()
        assert len(records) == 1
        assert records[0]["backup_path"] is None
        assert records[0]["kind"] == "my_kind"


@pytest.mark.unit
class TestSymlinkHandling:
    """corrupt 目标是 symlink 时, 不 rename (避免破坏下游 symlink 守卫).

    Regression: Sprint 9 ``test_save_pending_rejects_symlink_target``
    relies on ``_load_all`` leaving the symlink intact so that
    ``atomic_write_text``'s symlink-rejection guard can still fire.
    Renaming the symlink would destroy it and let the write succeed.
    """

    def test_corrupt_symlink_not_renamed(self, tmp_path: Path):
        # external target with corrupt content
        external = tmp_path / "external.json"
        external.write_text("not json", encoding="utf-8")

        # symlink: pending.json -> external.json
        link_path = tmp_path / "pending.json"
        link_path.symlink_to(external)

        result = safe_load_json(link_path, default={"d": 1}, kind="my_kind")
        assert result == {"d": 1}, "corrupt symlink 应返回 default"

        # symlink 应仍在原位 (没被 rename 走)
        assert link_path.is_symlink(), (
            "corrupt symlink 不应被 rename 走 (会破坏 atomic_write_text "
            "的 symlink 守卫)"
        )
        # 没有 .corrupt-* 备份被创建
        assert list(tmp_path.glob("*.corrupt-*")) == []

        # diagnostics 仍记录事件, 但 backup_path=None
        records = recent_state_file_corruption()
        assert len(records) == 1
        assert records[0]["backup_path"] is None

    def test_corrupt_symlink_does_not_modify_target(self, tmp_path: Path):
        """symlink 不动 target 文件 (target 是另一文件, 不应被旁路)."""
        external = tmp_path / "external.json"
        external.write_text("not json", encoding="utf-8")

        link_path = tmp_path / "pending.json"
        link_path.symlink_to(external)

        safe_load_json(link_path, default={}, kind="my_kind")

        # external.json 应仍在原位, 内容不变
        assert external.exists()
        assert external.read_text(encoding="utf-8") == "not json"
