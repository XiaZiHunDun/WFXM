"""EvalReport v1 unified schema (MOD-4)."""

from __future__ import annotations

import time
from typing import Any

from butler.contracts.eval_ports import SuiteRunResult

SCHEMA_VERSION = "1"


def build_unified_report(
    results: list[SuiteRunResult],
    *,
    sink_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    suites: dict[str, Any] = {}
    for r in results:
        suites[r.suite_id] = {
            "ok": r.ok,
            "layer": r.layer,
            "metrics": r.metrics,
            "sink_refs": r.sink_refs,
            "error": r.error or None,
        }
    reliability: dict[str, Any] = {}
    if "tcr" in suites:
        reliability["tcr"] = suites["tcr"].get("metrics", {}).get("trajectory_compliance_rate")
    if "agent_weekly" in suites:
        aw = suites["agent_weekly"].get("metrics", {})
        reliability["pass_at_3"] = aw.get("pass_at_3")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suites": suites,
        "dimensions": {
            "reliability": reliability,
            "safety": {
                "cup_strict": reliability.get("tcr"),
            },
        },
        "sinks": sink_status or {},
    }
