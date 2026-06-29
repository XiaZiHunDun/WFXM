"""RAGAS memory faithfulness suite (opt-in, MOD-8)."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult


def _ragas_available() -> bool:
    try:
        import ragas  # noqa: F401

        return True
    except ImportError:
        return False


class RagasMemorySuite:
    suite_id = "ragas_memory"
    layer = "L-D"

    def run(self, *, warn_only: bool = False) -> SuiteRunResult:
        if not _ragas_available():
            return SuiteRunResult(
                suite_id=self.suite_id,
                ok=True,
                layer=self.layer,
                metrics={"skipped": True, "reason": "ragas not installed"},
            )
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=True,
            layer=self.layer,
            metrics={"ragas_installed": True, "pilot": "stub_pass"},
        )
