"""Sprint 28 P1-3.4: /详细 --child <child_sk> UI 入口.

P1-3.4 gap 落地: 当前 /详细 只支持 report section (changes/decisions/issues),
不支持直接查看子 session transcript. child_session_key 在
/任务 / `make_child_session_key` / transcript_export 已完整, 缺 UI 入口.

覆盖:
  - parse_child_arg 解析 --child <sk> / --child=<sk> / --child <sk> <rest>
  - parse_child_arg 边界: 空 / 无 --child / --child 无值
  - format_child_session_detail 不存在 child_sk 优雅降级
  - format_child_session_detail 存在时输出 transcript 摘要
  - format_child_session_detail BUTLER_SESSION_TRANSCRIPT=0 关闭时优雅降级
  - 旧路径 parse_detail_section 不变 (3 case, 兼容回归)
"""

from __future__ import annotations

import pytest

from butler.report.format import (
    format_child_session_detail,
    parse_child_arg,
    parse_detail_section,
)


# ── parse_child_arg: 解析 ──


class TestParseChildArg:
    def test_space_form(self):
        """`--child foo` → ('', 'foo')."""
        remaining, child = parse_child_arg("--child foo")
        assert remaining == ""
        assert child == "foo"

    def test_equals_form(self):
        """`--child=foo` → ('', 'foo')."""
        remaining, child = parse_child_arg("--child=foo")
        assert remaining == ""
        assert child == "foo"

    def test_with_remaining_section(self):
        """`--child foo changes` → ('changes', 'foo')."""
        remaining, child = parse_child_arg("--child foo changes")
        assert remaining == "changes"
        assert child == "foo"

    def test_with_remaining_section_equals_form(self):
        """`--child=foo changes` → ('changes', 'foo')."""
        remaining, child = parse_child_arg("--child=foo changes")
        assert remaining == "changes"
        assert child == "foo"

    def test_empty_arg(self):
        """空 arg → ('', None)."""
        remaining, child = parse_child_arg("")
        assert remaining == ""
        assert child is None

    def test_no_child_flag(self):
        """无 --child 前缀 → (原 arg, None). 旧路径不变."""
        remaining, child = parse_child_arg("changes")
        assert remaining == "changes"
        assert child is None

    def test_section_keyword_unchanged(self):
        """section 关键字 (决策/问题 等) 不被误识别为 child_sk."""
        remaining, child = parse_child_arg("决策")
        assert remaining == "决策"
        assert child is None

    def test_flag_without_value(self):
        """`--child` 单独 (无 value) → ('--child', None), 视为无效."""
        remaining, child = parse_child_arg("--child")
        assert child is None

    def test_flag_with_empty_value(self):
        """`--child ` (空 value, 仅尾空格) → child=None."""
        remaining, child = parse_child_arg("--child ")
        assert child is None


# ── format_child_session_detail: 渲染 ──


class TestFormatChildSessionDetail:
    def test_nonexistent_child_sk_graceful_degrade(self, tmp_path, monkeypatch):
        """child_sk 不存在 (无 transcript.jsonl) → 优雅降级."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        out = format_child_session_detail("nonexistent-child-sk-xyz")
        # 应给个明确提示, 不抛
        assert "nonexistent-child-sk-xyz" in out
        assert "暂无" in out or "无" in out or "未找到" in out

    def test_existing_child_sk_renders_transcript(self, tmp_path, monkeypatch):
        """child_sk 存在且有 transcript → 渲染 markdown 摘要."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        from butler.core.session_transcript import record_generic_event

        sk = "parent::delegate::task-1"
        record_generic_event(
            sk,
            "delegate_started",
            {
                "task_id": "task-1",
                "child_session_key": sk,
                "parent_session_key": "parent",
                "role": "executor",
            },
        )
        record_generic_event(
            sk,
            "delegate_turn_done",
            {
                "task_id": "task-1",
                "child_session_key": sk,
                "parent_session_key": "parent",
                "success": True,
            },
        )

        out = format_child_session_detail(sk)
        # 应包含 child_sk + 至少一个 delegate 事件
        assert sk in out
        assert "delegate_started" in out or "delegate" in out

    def test_transcript_disabled_graceful_degrade(self, tmp_path, monkeypatch):
        """BUTLER_SESSION_TRANSCRIPT=0 时, 仍能返回友好提示而不抛."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "0")
        from butler.config import reload_butler_settings

        reload_butler_settings()
        out = format_child_session_detail("any-child-sk")
        # transcript 关闭时, 应给"已关闭"提示
        assert "已关闭" in out or "关闭" in out or "暂无" in out


# ── 旧路径不变: parse_detail_section 兼容回归 ──


class TestParseDetailSectionRegression:
    @pytest.mark.parametrize(
        "arg,expected",
        [
            ("", ""),
            ("changes", "changes"),
            ("变更", "changes"),
            ("decisions", "decisions"),
            ("issues", "issues"),
        ],
    )
    def test_parse_detail_section_unchanged(self, arg, expected):
        """旧 parse_detail_section 在 parse_child_arg 不动它, 行为不变."""
        assert parse_detail_section(arg) == expected
