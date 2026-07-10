"""Tests for Sprint 13 PERF-13-3: transcript 批量写.

设计：transcript_batch(session_key) 上下文管理器
- with 块内所有 record_*() 调用走 buffer，不立即写
- 块退出时一次性 flush（单次文件 open + 写）
- 块退出异常也 flush（finally 语义）
- 块外 record_*() 行为不变（立即写）
- 多个 session 的 batch 互不干扰
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_butler_home(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    yield tmp_path


# ── transcript_batch context manager API ───────────────────────


class TestTranscriptBatchContext:
    def test_batch_is_context_manager(self):
        from butler.core.session_transcript import transcript_batch

        # 必须能被 with 使用
        with transcript_batch("sk1"):
            pass

    def test_empty_batch_writes_nothing(self, temp_butler_home):
        from butler.core.session_transcript import (
            transcript_batch,
            transcript_path,
        )

        with transcript_batch("sk_empty"):
            pass

        path = transcript_path("sk_empty")
        # 空 batch 不应产生文件
        assert not path.exists() or path.stat().st_size == 0


# ── 批量写 vs 立即写 ─────────────────────────────────────────


class TestBatchVsImmediate:
    def test_inside_batch_does_not_write_immediately(self, temp_butler_home):
        from butler.core.session_transcript import (
            record_user_message,
            transcript_batch,
            transcript_path,
        )

        path = transcript_path("sk_b1")
        with transcript_batch("sk_b1"):
            record_user_message("sk_b1", "hello")
            record_user_message("sk_b1", "world")
            # 在 with 块内：文件应还不存在（或为空）
            assert not path.exists() or path.stat().st_size == 0

    def test_outside_batch_writes_immediately(self, temp_butler_home):
        from butler.core.session_transcript import (
            record_user_message,
            transcript_path,
        )

        path = transcript_path("sk_i1")
        record_user_message("sk_i1", "alone")
        # 块外：文件应立即存在
        assert path.exists()
        assert path.stat().st_size > 0

    def test_batch_flushes_on_exit(self, temp_butler_home):
        from butler.core.session_transcript import (
            record_user_message,
            transcript_batch,
            transcript_path,
        )

        path = transcript_path("sk_b2")
        with transcript_batch("sk_b2"):
            record_user_message("sk_b2", "msg-1")
            record_user_message("sk_b2", "msg-2")

        # 块退出后：应已 flush
        assert path.exists()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        rows = [json.loads(ln) for ln in lines]
        assert rows[0]["type"] == "user"
        assert rows[0]["content_preview"] == "msg-1"
        assert rows[1]["content_preview"] == "msg-2"

    def test_batch_flushes_on_exception(self, temp_butler_home):
        from butler.core.session_transcript import (
            record_user_message,
            transcript_batch,
            transcript_path,
        )

        path = transcript_path("sk_b3")
        with pytest.raises(RuntimeError):
            with transcript_batch("sk_b3"):
                record_user_message("sk_b3", "before-error")
                raise RuntimeError("boom")

        # 即使异常，也应 flush
        assert path.exists()
        rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]
        assert rows[0]["content_preview"] == "before-error"


# ── 批量写一次 vs N 次（核心 PERF 指标）──────────────────────


class TestBatchReducesWrites:
    def test_n_records_one_file_open(self, temp_butler_home):
        """N 条记录应只触发 1 次 _flush_entries（batch 合并）。"""
        from butler.core import session_transcript
        from butler.core.session_transcript import (
            record_user_message,
            transcript_batch,
        )

        flushes: list[str] = []
        original_flush = session_transcript._flush_entries

        def counting_flush(sk, entries):
            flushes.append(sk)
            return original_flush(sk, entries)

        with patch.object(session_transcript, "_flush_entries", counting_flush):
            with transcript_batch("sk_perf1"):
                for i in range(5):
                    record_user_message("sk_perf1", f"msg-{i}")

        # 5 条 record → 1 次 _flush_entries 调用（块退出时）
        assert len(flushes) == 1

    def test_5_records_outside_batch_5_appends(self, temp_butler_home):
        """对比：块外 5 条 record → 5 次 _append_line（无 batch 合并）。"""
        from butler.core import session_transcript
        from butler.core.session_transcript import record_user_message

        appends: list[str] = []
        original_append_line = session_transcript._append_line

        def counting_append_line(path, entry):
            appends.append(str(path))
            return original_append_line(path, entry)

        with patch.object(session_transcript, "_append_line", counting_append_line):
            for i in range(5):
                record_user_message("sk_perf2", f"msg-{i}")

        assert len(appends) == 5


# ── 多种 record_* 混用 ─────────────────────────────────────


class TestMixedRecordsInBatch:
    def test_mixed_record_types(self, temp_butler_home):
        from butler.core.session_transcript import (
            record_assistant_message,
            record_tool_action,
            record_tool_observation,
            record_user_message,
            transcript_batch,
            transcript_path,
        )

        with transcript_batch("sk_mix"):
            record_user_message("sk_mix", "u")
            record_assistant_message("sk_mix", "a", tool_calls=1)
            record_tool_action("sk_mix", tool_name="read_file")
            record_tool_observation("sk_mix", tool="read_file", ok=True, preview="out")

        rows = [
            json.loads(ln)
            for ln in transcript_path("sk_mix").read_text(encoding="utf-8").splitlines()
        ]
        types = [r["type"] for r in rows]
        assert types == ["user", "assistant", "tool_action", "tool_observation"]


# ── 多个 session 的 batch 互不干扰 ─────────────────────────


class TestMultipleSessions:
    def test_independent_session_batches(self, temp_butler_home):
        from butler.core.session_transcript import (
            record_user_message,
            transcript_batch,
            transcript_path,
        )

        with transcript_batch("sk_a"):
            record_user_message("sk_a", "a-1")
            record_user_message("sk_a", "a-2")
        with transcript_batch("sk_b"):
            record_user_message("sk_b", "b-1")

        rows_a = [
            json.loads(ln)
            for ln in transcript_path("sk_a").read_text(encoding="utf-8").splitlines()
        ]
        rows_b = [
            json.loads(ln)
            for ln in transcript_path("sk_b").read_text(encoding="utf-8").splitlines()
        ]
        assert [r["content_preview"] for r in rows_a] == ["a-1", "a-2"]
        assert [r["content_preview"] for r in rows_b] == ["b-1"]


# ── 嵌套 batch 行为 ─────────────────────────────────────────


class TestNestedBatches:
    def test_nested_batches(self, temp_butler_home):
        """嵌套 batch：内层退出时 flush，外层退出时 flush 内层之后的增量。"""
        from butler.core.session_transcript import (
            record_user_message,
            transcript_batch,
            transcript_path,
        )

        with transcript_batch("sk_nest"):
            record_user_message("sk_nest", "outer-1")
            with transcript_batch("sk_nest"):
                record_user_message("sk_nest", "inner-1")
            record_user_message("sk_nest", "outer-2")

        rows = [
            json.loads(ln)
            for ln in transcript_path("sk_nest").read_text(encoding="utf-8").splitlines()
        ]
        previews = [r["content_preview"] for r in rows]
        assert previews == ["outer-1", "inner-1", "outer-2"]


# ── 线程安全：并发 batch 互不干扰 ─────────────────────────


class TestThreadSafety:
    def test_concurrent_batches_dont_mix(self, temp_butler_home):
        from butler.core.session_transcript import (
            record_user_message,
            transcript_batch,
            transcript_path,
        )

        def writer(sk, n):
            with transcript_batch(sk):
                for i in range(n):
                    record_user_message(sk, f"{sk}-{i}")

        threads = [
            threading.Thread(target=writer, args=(f"sk_t{i}", 10))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i in range(3):
            sk = f"sk_t{i}"
            rows = [
                json.loads(ln)
                for ln in transcript_path(sk).read_text(encoding="utf-8").splitlines()
            ]
            previews = [r["content_preview"] for r in rows]
            assert previews == [f"{sk}-{i}" for i in range(10)]


# ── 完整 turn 集成：user→tool→observation→assistant → 1 write ──


class TestFullTurnBatch:
    def test_full_turn_sequence_one_flush(self, temp_butler_home):
        """模拟一整轮 turn：user + 2 tool actions + 2 observations + assistant
        → 只触发 1 次 _flush_entries。
        """
        from butler.core import session_transcript
        from butler.core.session_transcript import (
            record_assistant_message,
            record_tool_action,
            record_tool_observation,
            record_user_message,
            transcript_batch,
            transcript_path,
        )

        flushes: list[str] = []
        original_flush = session_transcript._flush_entries

        def counting_flush(sk, entries):
            flushes.append(sk)
            return original_flush(sk, entries)

        with patch.object(session_transcript, "_flush_entries", counting_flush):
            with transcript_batch("sk_turn1"):
                # agent_loop._run_turn_body 内的事件序列
                record_user_message("sk_turn1", "用户问题")
                record_tool_action("sk_turn1", tool_name="read_file")
                record_tool_action("sk_turn1", tool_name="list_directory")
                record_tool_observation("sk_turn1", tool="read_file", ok=True, preview="...")
                record_tool_observation(
                    "sk_turn1", tool="list_directory", ok=True, preview="..."
                )
                record_assistant_message("sk_turn1", "助手回答", tool_calls=2)

        # 1 次 _flush（turn 边界）
        assert len(flushes) == 1

        # 验证内容：6 行按顺序写入
        rows = [
            json.loads(ln)
            for ln in transcript_path("sk_turn1").read_text(encoding="utf-8").splitlines()
        ]
        types = [r["type"] for r in rows]
        assert types == [
            "user",
            "tool_action",
            "tool_action",
            "tool_observation",
            "tool_observation",
            "assistant",
        ]
