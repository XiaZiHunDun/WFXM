"""Agent weekly KPI suite (TCR + Pass@3)."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult


class AgentWeeklySuite:
    suite_id = "agent_weekly"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        from butler.ops.agent_eval_weekly import build_weekly_report

        report = build_weekly_report()
        dims = report.get("dimensions") or {}
        rel = dims.get("reliability") or {}
        ok = True
        tcr = rel.get("tcr")
        if tcr is not None and float(tcr) < 0.98 and not warn_only:
            ok = False
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics={
                "tcr": rel.get("tcr"),
                "pass_at_3": rel.get("pass_at_3"),
                "cup_strict": (dims.get("safety") or {}).get("cup_strict"),
            },
        )
