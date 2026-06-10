"""A2: skill lint warn-only."""

from __future__ import annotations

from butler.skills.lint import format_lint_report, lint_skill_summaries


def test_warns_missing_preferred_tools_when_triggers_present():
    issues = lint_skill_summaries(
        [
            {
                "name": "demo",
                "triggers": ["demo"],
                "preferred_tools": [],
            },
            {
                "name": "ok",
                "triggers": [],
                "preferred_tools": ["read_file"],
            },
        ]
    )
    assert len(issues) == 1
    assert issues[0].skill_name == "demo"
    assert issues[0].code == "missing_preferred_tools"


def test_format_report_pass():
    assert "通过" in format_lint_report([])
