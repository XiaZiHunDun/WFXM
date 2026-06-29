"""EvalIntegrationManager tests."""

from __future__ import annotations

from unittest.mock import patch

from butler.eval_integration.manager import EvalIntegrationManager
from butler.eval_integration.report_schema import SCHEMA_VERSION, build_unified_report
from butler.contracts.eval_ports import SuiteRunResult


def test_build_unified_report_schema():
    results = [
        SuiteRunResult(
            suite_id="tcr",
            ok=True,
            layer="L-B",
            metrics={"trajectory_compliance_rate": 1.0},
        ),
    ]
    report = build_unified_report(results)
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["suites"]["tcr"]["ok"] is True
    assert report["dimensions"]["reliability"]["tcr"] == 1.0


def test_manager_list_suites():
    mgr = EvalIntegrationManager()
    ids = mgr.list_suites()
    assert "tcr" in ids
    assert "agent_weekly" in ids


@patch("butler.eval_integration.suites.tcr_suite.TcrSuite.run")
def test_manager_run_tcr_mock(mock_run, tmp_path):
    mock_run.return_value = SuiteRunResult(
        suite_id="tcr",
        ok=True,
        layer="L-B",
        metrics={"trajectory_compliance_rate": 1.0},
    )
    mgr = EvalIntegrationManager(sinks=[])
    report, results = mgr.run_and_write(["tcr"], out=tmp_path / "eval.json")
    assert results[0].ok
    assert (tmp_path / "eval.json").is_file()
    assert report["suites"]["tcr"]["ok"] is True
