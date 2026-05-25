"""PR-F5: outcome log + handoff dependency context."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from butler.experiments.outcomes import (
    append_pending,
    format_context_for_prompt,
    list_pending,
    resolve_outcome,
)
from butler.report import enrich_report_decisions, parse_decisions_from_text
from butler.task_orchestrator import AgentReport, AgentResult, _format_dependency_context


def test_outcome_pending_resolve_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        row = append_pending(
            ws,
            project="demo",
            subject="job-1",
            hypothesis="improve latency",
            source="test",
        )
        assert row["status"] == "pending"
        assert list_pending(ws, project="demo")

        resolved = resolve_outcome(
            ws,
            row_id=row["row_id"],
            outcome_value="0.42",
            reflection="latency improved",
            project="demo",
        )
        assert resolved is not None
        assert resolved["status"] == "resolved"
        assert not list_pending(ws, project="demo")

        ctx = format_context_for_prompt(ws, project="demo")
        assert "outcome log" in ctx
        assert "0.42" in ctx or "latency improved" in ctx


def test_parse_decisions_from_text():
    text = "Final **Rating**: approve with notes"
    assert "approve" in parse_decisions_from_text(text)


def test_handoff_only_dependency_context():
    report = AgentReport(
        headline="step-a done",
        summary="implemented feature X",
        success=True,
    )
    dep = AgentResult(success=True, response="long " * 500, report=report)
    block = _format_dependency_context("step-a", dep, handoff_only=True)
    assert "## Handoff" in block
    assert "long " * 100 not in block

    plain = _format_dependency_context("step-a", dep, handoff_only=False)
    assert "[step-a 结果]" in plain


def test_enrich_report_decisions():
    rep = AgentReport()
    enrich_report_decisions(rep, "**Rating**: keep")
    assert "keep" in rep.decisions
