"""L1 unit tests for butler.report."""

import pytest

import butler.report as report_mod
from butler.report import (
    AgentReport,
    Change,
    cache_report,
    clear_report_cache,
    format_detail,
    format_for_butler_tool_result,
    format_for_cli,
    format_for_wechat,
    get_last_report,
)


@pytest.fixture(autouse=True)
def _clear_report_cache():
    report_mod.clear_report_cache()
    yield
    report_mod.clear_report_cache()


@pytest.mark.unit
class TestAgentReport:
    def test_creation_with_all_fields(self):
        report = AgentReport(
            headline="Done",
            changes=[Change("a.py", "modified", "fix bug")],
            decisions=["Use pytest"],
            issues=["Flaky test"],
            summary="All good",
            success=True,
            iterations=2,
            tool_calls=4,
            tokens_used=900,
            elapsed_seconds=3.5,
        )
        assert report.headline == "Done"
        assert len(report.changes) == 1
        assert report.iterations == 2
        assert report.tokens_used == 900

    def test_to_dict_round_trip(self, sample_report):
        d = sample_report.to_dict()
        restored = AgentReport.from_dict(d)
        assert restored.headline == sample_report.headline
        assert len(restored.changes) == len(sample_report.changes)
        assert restored.changes[0].file == "main.py"
        assert restored.decisions == sample_report.decisions
        assert restored.success == sample_report.success
        assert restored.task_preview == sample_report.task_preview

    def test_from_dict_accepts_desc_key(self):
        data = {
            "headline": "Update",
            "changes": [{"file": "x.py", "action": "created", "desc": "New module"}],
        }
        report = AgentReport.from_dict(data)
        assert report.changes[0].description == "New module"


@pytest.mark.unit
class TestChange:
    def test_dataclass_fields(self):
        c = Change(file="lib.py", action="deleted", description="Remove dead code")
        assert c.file == "lib.py"
        assert c.action == "deleted"
        assert c.description == "Remove dead code"


@pytest.mark.unit
class TestFormatters:
    def test_format_for_cli_contains_headline_and_files(self, sample_report):
        text = format_for_cli(sample_report)
        assert sample_report.headline in text
        assert "main.py" in text
        assert "utils.py" in text

    def test_format_for_wechat_contains_headline(self, sample_report):
        text = format_for_wechat(sample_report)
        assert sample_report.headline in text

    def test_format_for_wechat_shows_issues_on_failure(self):
        report = AgentReport(
            headline="开发代理未能完成任务",
            success=False,
            issues=["File not found: docs/x.txt"],
        )
        text = format_for_wechat(report)
        assert "未能完成任务" in text
        assert "File not found" in text

    def test_format_detail_includes_task_preview(self):
        report = AgentReport(
            headline="开发代理已完成任务",
            task_preview="删除 docs/test_hello.txt",
            summary="已删除",
        )
        text = format_detail(report)
        assert "【本报告任务】删除 docs/test_hello.txt" in text

    def test_format_detail_contains_execution_stats(self, sample_report):
        text = format_detail(sample_report)
        assert "执行统计" in text
        assert "1,500" in text or "1500" in text

    def test_format_detail_changes_section(self, sample_report):
        text = format_detail(sample_report, section="changes")
        assert "文件变更详情" in text
        assert "main.py" in text

    def test_format_detail_decisions_section(self, sample_report):
        text = format_detail(sample_report, section="decisions")
        assert "关键决策" in text
        assert "dataclass" in text

    def test_format_detail_issues_section(self, sample_report):
        text = format_detail(sample_report, section="issues")
        assert "需关注的问题" in text
        assert "unit tests" in text

    def test_format_for_butler_tool_result(self, sample_report):
        d = format_for_butler_tool_result(sample_report)
        assert d["headline"] == sample_report.headline
        assert d["changes_count"] == len(sample_report.changes)
        assert "changes" in d


@pytest.mark.unit
class TestReportCache:
    def test_cache_and_get_last_report(self, sample_report):
        assert get_last_report() is None
        cache_report(sample_report)
        cached = get_last_report()
        assert cached is sample_report
        assert cached.headline == sample_report.headline

    def test_cache_isolated_by_session_key(self, sample_report):
        clear_report_cache()
        other = AgentReport(headline="other session")
        cache_report(sample_report, session_key="wechat:user1:alpha")
        cache_report(other, session_key="wechat:user2:beta")
        assert get_last_report("wechat:user1:alpha") is sample_report
        assert get_last_report("wechat:user2:beta") is other
        assert get_last_report("wechat:user1:alpha").headline != other.headline
