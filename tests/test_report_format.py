"""Sprint 2: WeChat report formatting and /detail sections."""

from __future__ import annotations

import pytest

from butler.core.loop_types import LoopResult, LoopStatus
from butler.report import AgentReport, Change, cache_report, clear_report_cache, format_detail
from butler.report.format import parse_detail_section, turn_used_delegate_task, wechat_response_text


@pytest.fixture(autouse=True)
def _isolate_report_cache():
    clear_report_cache()
    yield
    clear_report_cache()


@pytest.mark.module_test
class TestDetailSectionParse:
    @pytest.mark.parametrize(
        "arg,expected",
        [
            ("", ""),
            ("changes", "changes"),
            ("变更", "changes"),
            ("decisions", "decisions"),
            ("决策", "decisions"),
            ("issues", "issues"),
            ("问题", "issues"),
        ],
    )
    def test_parse(self, arg, expected):
        assert parse_detail_section(arg) == expected


@pytest.mark.module_test
class TestWechatReportFormat:
    def test_turn_used_delegate_detects_tool_call(self):
        result = LoopResult(
            status=LoopStatus.COMPLETED,
            messages=[
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "1",
                            "type": "function",
                            "function": {"name": "delegate_task", "arguments": "{}"},
                        }
                    ],
                }
            ],
        )
        assert turn_used_delegate_task(result) is True

    def test_wechat_uses_compact_report_after_delegate(self):
        cache_report(
            AgentReport(
                headline="dev 代理完成任务",
                changes=[Change(file="a.py", action="created", description="")],
                summary="很长的详细总结" * 100,
            )
        )
        result = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="很长的详细总结" * 100,
            messages=[
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "1",
                            "function": {"name": "delegate_task", "arguments": "{}"},
                        }
                    ],
                }
            ],
        )
        text = wechat_response_text(result)
        assert "dev 代理完成任务" in text
        assert "新建1个文件" in text
        assert "详细" in text
        assert len(text) <= 2000

    def test_wechat_plain_text_without_delegate(self):
        cache_report(AgentReport(headline="old report"))
        result = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="普通回复",
            messages=[{"role": "assistant", "content": "普通回复"}],
        )
        assert wechat_response_text(result) == "普通回复"


@pytest.mark.module_test
class TestFormatDetailSections:
    def test_changes_section(self):
        report = AgentReport(
            changes=[Change(file="x.py", action="modified", description="fix")],
        )
        out = format_detail(report, section="changes")
        assert "x.py" in out
        assert "modified" in out or "~" in out
