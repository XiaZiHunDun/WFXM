"""PROD-P4-C: memory auto-approve + Owner PMF metrics."""

from __future__ import annotations

import json

import pytest


@pytest.mark.unit
def test_memory_auto_approve_correction_mode(tmp_path, monkeypatch):
    from butler.memory.project_memory import MarkdownMemory

    monkeypatch.setenv("BUTLER_MEMORY_AUTO_APPROVE", "correction")
    mm = MarkdownMemory(tmp_path / "MEMORY.md")
    assert mm.append("Notes", "默认测试框架为 pytest", classification="auto") == "pending"
    assert mm.append("Notes", "请记住：称呼主公", classification="auto") == "fact"
    assert len(mm.list_pending()) == 1


@pytest.mark.unit
def test_memory_auto_approve_all_mode(tmp_path, monkeypatch):
    from butler.memory.project_memory import MarkdownMemory

    monkeypatch.setenv("BUTLER_MEMORY_AUTO_APPROVE", "all")
    mm = MarkdownMemory(tmp_path / "MEMORY.md")
    assert mm.append("Notes", "低风险偏好 pytest", classification="auto") == "fact"


@pytest.mark.unit
def test_owner_pmf_metrics_opt_in(monkeypatch):
    monkeypatch.setenv("BUTLER_OWNER_PMF_METRICS", "1")

    from butler.config import get_butler_home
    from butler.ops.owner_pmf_metrics import (
        format_owner_pmf_report,
        record_brief_view,
        record_acceptance_card,
        summarize_owner_pmf,
    )
    from butler.report.acceptance_card import attach_delegate_acceptance_meta
    from butler.report.generator import AgentReport, Change

    record_brief_view(session_key="wechat:u:1")
    report = AgentReport(
        headline="ok",
        success=True,
        task_id="t1",
        changes=[Change(file="a.py", action="modified", description="")],
    )
    attach_delegate_acceptance_meta(
        report,
        role="dev",
        project=type("P", (), {"dev": {"test_command": "pytest"}})(),
        dev_engine={"verify_passed": True, "edits": 1},
    )
    record_acceptance_card(report, session_key="wechat:u:1")

    s = summarize_owner_pmf(days=7)
    assert s["brief_days"] >= 1
    assert s["acceptance_card_total"] >= 1
    assert s["acceptance_verify_ok"] >= 1

    text = format_owner_pmf_report(days=7)
    assert "PMF 周报" in text
    assert "简报" in text

    jsonl = list((get_butler_home() / "metrics").glob("owner_pmf_*.jsonl"))
    assert jsonl
    rows = [json.loads(ln) for ln in jsonl[0].read_text().splitlines() if ln.strip()]
    assert any(r.get("event") == "brief" for r in rows)


@pytest.mark.unit
def test_owner_pmf_feedback_retry(monkeypatch):
    monkeypatch.setenv("BUTLER_OWNER_PMF_METRICS", "1")

    from butler.ops.owner_pmf_metrics import (
        maybe_record_post_feedback_retry,
        record_owner_feedback_pmf,
        summarize_owner_pmf,
    )

    sk = "wechat:owner:retry"
    record_owner_feedback_pmf(session_key=sk, trigger="owner_hard_feedback")
    maybe_record_post_feedback_retry("/改 docs/x.md 修一行", session_key=sk)

    s = summarize_owner_pmf(days=7)
    assert s["feedback_count"] >= 1
    assert s["feedback_retry_count"] >= 1
