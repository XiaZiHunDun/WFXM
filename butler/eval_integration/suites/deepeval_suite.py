"""DeepEval agent metrics suite (opt-in, MOD-8)."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult


def _deepeval_available() -> bool:
    try:
        import deepeval  # noqa: F401

        return True
    except ImportError:
        return False


class DeepEvalAgentSuite:
    suite_id = "deepeval_agent"
    layer = "L-D"

    def run(self, *, warn_only: bool = False) -> SuiteRunResult:
        if not _deepeval_available():
            return SuiteRunResult(
                suite_id=self.suite_id,
                ok=True,
                layer=self.layer,
                metrics={"skipped": True, "reason": "deepeval not installed"},
            )
        # Pilot: structural pass when package present; full metric harness in follow-up PR
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=True,
            layer=self.layer,
            metrics={"deepeval_installed": True, "pilot": "stub_pass"},
        )
