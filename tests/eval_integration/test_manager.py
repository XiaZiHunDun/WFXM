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


@patch("butler.ops.eval_regression.run_regression_gate")
def test_regression_suite_mock(mock_run):
    from butler.eval_integration.suites.regression_suite import RegressionSuite
    from butler.ops.eval_regression import RegressionReport

    mock_run.return_value = RegressionReport(
        passed=True,
        dev_pass_rate=0.9,
        mem_pass_rate=0.8,
    )
    result = RegressionSuite().run(push_langfuse=False)
    assert result.ok
    assert result.suite_id == "regression"


def test_manager_list_includes_regression_wechat():
    mgr = EvalIntegrationManager()
    ids = mgr.list_suites()
    assert "tcr" in ids
    assert "regression" in ids
    assert "wechat_corpus" in ids


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
