"""Sprint 16 TST-11-6: butler.__init__ format_build_identity_line / mark_start_time 0%.

bug: butler/__init__.py:55-57, 60-63
  - format_build_identity_line 和 mark_start_time 没有任何测试覆盖
  - 关键路径: gateway/runner.py:120 在启动日志里调用 format_build_identity_line
  - 失败会留下空日志 / 误导性诊断信息

修复: 直接补单测覆盖两个函数, 不改实现 (它们已经正确)。
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

import butler
import butler as butler_init  # 模块对象, 可写属性


@pytest.fixture(autouse=True)
def _reset_module_state():
    """每个测试前后重置模块级缓存, 避免 _git_sha / _start_time 污染。"""
    butler._git_sha = None
    butler._start_time = None
    yield
    butler._git_sha = None
    butler._start_time = None


# ── format_build_identity_line 覆盖 ──


class TestFormatBuildIdentityLine:
    def test_format_with_known_sha(self):
        """已知 git SHA 时, 输出应含 Butler v{version} (commit={sha}, python={py})。"""
        with patch.object(butler_init, "_resolve_git_sha", return_value="abc1234"):
            line = butler_init.format_build_identity_line()
        assert line.startswith(f"Butler v{butler_init.__version__} ")
        assert "commit=abc1234" in line
        assert "python=" in line
        # python 字段应是 X.Y.Z 形式
        import re

        assert re.search(r"python=\d+\.\d+\.\d+", line), line

    def test_format_with_unknown_sha(self):
        """git 不可用时, sha 应是 'unknown' 但格式仍正确。"""
        with patch.object(butler_init, "_resolve_git_sha", return_value="unknown"):
            line = butler_init.format_build_identity_line()
        assert "commit=unknown" in line
        assert "Butler v" in line

    def test_format_caches_sha_across_calls(self):
        """重复调用 format_build_identity_line 不应再调 subprocess (git)。"""
        call_count = {"n": 0}

        def fake_check_output(*args, **kwargs):
            call_count["n"] += 1
            return b"deadbee\n"

        with patch.object(butler_init.subprocess, "check_output", side_effect=fake_check_output):
            butler_init.format_build_identity_line()
            butler_init.format_build_identity_line()
            butler_init.format_build_identity_line()
        # 第一次 resolve 后, _git_sha 缓存; 后续不应再调 git
        assert call_count["n"] == 1, (
            f"subprocess.check_output 应只调 1 次 (module cache), 实际 {call_count['n']}"
        )

    def test_format_handles_git_subprocess_failure(self):
        """git rev-parse 抛错时, sha 应是 'unknown' (不应让 gateway 启动崩溃)。"""
        def raise_called_process_error(*a, **kw):
            raise butler_init.subprocess.CalledProcessError(128, "git")

        with patch.object(
            butler_init.subprocess, "check_output", side_effect=raise_called_process_error,
        ):
            line = butler_init.format_build_identity_line()
        assert "commit=unknown" in line, (
            f"git 失败时 sha 应为 'unknown', 实际: {line}"
        )


# ── mark_start_time 覆盖 ──


class TestMarkStartTime:
    def test_mark_sets_start_time_to_utc_now(self):
        """mark_start_time 应把 _start_time 设为当前 UTC 时间。"""
        before = datetime.datetime.now(tz=datetime.timezone.utc)
        butler_init.mark_start_time()
        after = datetime.datetime.now(tz=datetime.timezone.utc)

        assert butler_init._start_time is not None
        # 时区: 必须带 tzinfo=UTC
        assert butler_init._start_time.tzinfo is not None
        assert butler_init._start_time.utcoffset() == datetime.timedelta(0)
        # 时间窗口: 在 [before, after] 内
        assert before <= butler_init._start_time <= after, (
            f"start_time {butler_init._start_time} not in [{before}, {after}]"
        )

    def test_mark_overrides_existing_start_time(self):
        """重复 mark_start_time 应覆盖前值 (用于测试隔离 / 重启场景)。"""
        butler_init._start_time = datetime.datetime(
            2020, 1, 1, tzinfo=datetime.timezone.utc,
        )
        old = butler_init._start_time

        butler_init.mark_start_time()
        assert butler_init._start_time is not None
        assert butler_init._start_time != old, (
            "mark_start_time 应覆盖旧值, 但 _start_time 未变"
        )

    def test_format_uses_marked_start_time(self):
        """get_build_identity 的 start_time 字段应等于 mark_start_time 设置的值。"""
        butler_init.mark_start_time()
        marked = butler_init._start_time
        assert marked is not None

        info = butler_init.get_build_identity()
        assert info["start_time"] == marked.isoformat()
