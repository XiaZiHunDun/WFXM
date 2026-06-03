"""Sprint 16 TST-11-11: audit.write_run_record + latest_run 直测补全.

之前仅 lock 流程有测试 (sprint9/16), run record 写入/读取无直测.
覆盖:
  - write_run_record: 路径格式 / atomic write / nested dir 创建
  - latest_run: 缺 dir / 空 dir / 多文件取最新 / OSError 容忍 / 坏 JSON 容忍
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def mock_butler_home(tmp_path, monkeypatch):
    """Override get_butler_settings().butler_home to a tmp dir.

    注意: audit.py 用 ``from butler.config import get_butler_settings``,
    必须在 audit 模块 patch 而不是 config 模块 (Sprint 16 _tenant_store
    fixture 同款教训).
    """
    from butler.runtime import audit

    fake_home = tmp_path / "butler_home"
    fake_home.mkdir()
    settings = type("S", (), {"butler_home": fake_home})()
    monkeypatch.setattr(audit, "get_butler_settings", lambda: settings)
    return fake_home


# ── write_run_record ──


class TestWriteRunRecord:
    def test_creates_nested_dirs(self, mock_butler_home: Path):
        from butler.runtime.audit import write_run_record

        path = write_run_record(
            project_name="demo",
            job_id="j1",
            payload={"status": "ok"},
        )
        assert path.is_file()
        assert path.parent.parent.name == "demo"
        assert path.parent.name == "j1"

    def test_payload_serialized_to_json(self, mock_butler_home: Path):
        from butler.runtime.audit import write_run_record

        payload = {"status": "ok", "duration_ms": 1234, "tags": ["a", "b"]}
        path = write_run_record(project_name="p", job_id="j", payload=payload)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded == payload

    def test_unicode_payload_preserved(self, mock_butler_home: Path):
        from butler.runtime.audit import write_run_record

        path = write_run_record(
            project_name="项目",
            job_id="任务",
            payload={"msg": "你好"},
        )
        assert path.is_file()
        assert "项目" in str(path)
        assert "任务" in str(path)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["msg"] == "你好"

    def test_filename_uses_utc_timestamp(self, mock_butler_home: Path):
        from butler.runtime.audit import write_run_record

        path = write_run_record(project_name="p", job_id="j", payload={})
        # 文件名形如 20260603T120000Z.json
        assert path.suffix == ".json"
        stem = path.stem
        assert stem.endswith("Z")
        # 14 位 UTC 时间戳 YYYYMMDDTHHMMSS
        ts = stem[:-1]  # 去 Z
        assert len(ts) == 15
        assert ts[8] == "T"

    def test_special_chars_in_project_name_slugged(self, mock_butler_home: Path):
        """project_name 被 slug (非字母数字 → _), job_id 保持原样."""
        from butler.runtime.audit import write_run_record

        path = write_run_record(
            project_name="my project/special@x",
            job_id="job#1",  # job_id 不 slug, 保留 #
            payload={},
        )
        assert "my_project_special_x" in str(path)
        assert "job#1" in str(path)  # job_id 字面保留
        # 验证文件确实在 slug 后的 project 目录下
        assert path.parent.parent.name == "my_project_special_x"
        assert path.parent.name == "job#1"


# ── latest_run ──


class TestLatestRun:
    def test_returns_none_when_dir_missing(self, mock_butler_home: Path):
        from butler.runtime.audit import latest_run

        assert latest_run("nonexistent", "j1") is None

    def test_returns_none_when_dir_empty(self, mock_butler_home: Path):
        from butler.runtime.audit import latest_run

        empty = mock_butler_home / "runtime" / "runs" / "p" / "j1"
        empty.mkdir(parents=True)
        assert latest_run("p", "j1") is None

    def test_returns_payload_of_latest_file(self, mock_butler_home: Path):
        from butler.runtime.audit import write_run_record, latest_run

        # 写两条, 间隔 1s 保证时间戳不同
        write_run_record(project_name="p", job_id="j1", payload={"n": 1})
        time.sleep(1.05)  # UTC 秒级时间戳
        write_run_record(project_name="p", job_id="j1", payload={"n": 2})

        result = latest_run("p", "j1")
        assert result == {"n": 2}

    def test_returns_none_on_corrupt_json(self, mock_butler_home: Path):
        from butler.runtime.audit import latest_run

        d = mock_butler_home / "runtime" / "runs" / "p" / "j1"
        d.mkdir(parents=True)
        # 写一个 latest 文件但内容坏
        (d / "20260101T000000Z.json").write_text("{not json", encoding="utf-8")
        assert latest_run("p", "j1") is None

    def test_returns_none_on_oserror(self, mock_butler_home: Path):
        from butler.runtime import audit

        # 模拟 latest_run 内部 read_text 抛 OSError
        d = mock_butler_home / "runtime" / "runs" / "p" / "j1"
        d.mkdir(parents=True)
        (d / "20260101T000000Z.json").write_text("{}", encoding="utf-8")

        with patch.object(Path, "read_text", side_effect=OSError("boom")):
            assert audit.latest_run("p", "j1") is None
