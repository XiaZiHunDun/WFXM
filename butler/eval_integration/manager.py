"""Eval integration manager — multi-sink orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.contracts.eval_ports import ScoreSinkPort, SuiteRunResult
from butler.eval_integration.report_schema import build_unified_report
from butler.eval_integration.suite_registry import get_suite, list_suite_ids
from butler.eval_integration.sinks.audit_sink import AuditSink
from butler.eval_integration.sinks.junit_sink import JUnitSink
from butler.eval_integration.sinks.langfuse_sink import LangFuseSink

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / ".butler" / "reports" / "eval-unified.json"


class EvalIntegrationManager:
    def __init__(self, sinks: list[ScoreSinkPort] | None = None) -> None:
        self._sinks: list[ScoreSinkPort] = sinks or [
            AuditSink(),
            JUnitSink(),
            LangFuseSink(),
        ]

    def list_suites(self) -> list[str]:
        return list_suite_ids()

    def run_suites(
        self,
        suite_ids: list[str],
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> list[SuiteRunResult]:
        results: list[SuiteRunResult] = []
        for sid in suite_ids:
            suite = get_suite(sid)
            result = suite.run(
                warn_only=warn_only,
                sync_dataset=sync_dataset,
                push_langfuse=push_langfuse,
            )
            payload = {"suite_id": sid, "metrics": result.metrics, "ok": result.ok}
            for sink in self._sinks:
                if sink.backend_id == "langfuse" and sid not in (
                    "agent_weekly",
                    "regression",
                    "wechat_corpus",
                    "tcr",
                ):
                    continue
                try:
                    ref = sink.write_suite_result(result, payload)
                    if ref:
                        result.sink_refs[sink.backend_id] = ref
                except Exception:
                    pass
            results.append(result)
        return results

    def build_report(
        self,
        results: list[SuiteRunResult],
    ) -> dict[str, Any]:
        sink_status = {s.backend_id: {"registered": True} for s in self._sinks}
        return build_unified_report(results, sink_status=sink_status)

    def run_and_write(
        self,
        suite_ids: list[str],
        *,
        out: Path = DEFAULT_REPORT,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> tuple[dict[str, Any], list[SuiteRunResult]]:
        results = self.run_suites(
            suite_ids,
            warn_only=warn_only,
            sync_dataset=sync_dataset,
            push_langfuse=push_langfuse,
        )
        for r in results:
            if r.suite_id == "tcr":
                rate = r.metrics.get("trajectory_compliance_rate")
                if rate is not None:
                    try:
                        from butler.core.transform_feedback import analyse_transform_signals

                        analyse_transform_signals(tcr_rate=float(rate))
                    except Exception:
                        pass
        report = self.build_report(results)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report, results

    def sync_check(self, suite_id: str) -> dict[str, Any]:
        """Weak consistency check across sinks."""
        out: dict[str, Any] = {"suite_id": suite_id, "sinks": {}}
        for sink in self._sinks:
            latest = sink.read_latest(suite_id)
            out["sinks"][sink.backend_id] = {"present": latest is not None}
        return out
