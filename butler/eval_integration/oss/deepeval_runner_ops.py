"""DeepEval LLM pilot best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any


def run_llm_pilot_assert_safe(
    *,
    test_case: Any,
    metric: Any,
    warn_only: bool,
    threshold: float,
    pilot_case: str | None,
) -> tuple[bool, dict[str, Any]]:
    try:
        from deepeval import assert_test

        assert_test(test_case, [metric])
        return True, {
            "mode": "llm_pilot",
            "pass_rate": 1.0,
            "threshold": threshold,
            "pilot_case": pilot_case,
            "deepeval_installed": True,
        }
    except Exception as exc:
        if warn_only:
            return True, {
                "mode": "llm_pilot",
                "pass_rate": 0.0,
                "threshold": threshold,
                "warn_only": True,
                "error": str(exc)[:200],
            }
        return False, {
            "mode": "llm_pilot",
            "pass_rate": 0.0,
            "threshold": threshold,
            "error": str(exc)[:200],
        }
