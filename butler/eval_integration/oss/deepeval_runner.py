"""DeepEval agent metrics pilot — deterministic trajectory checks + optional LLM."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from butler.env_parse import float_env

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "deepeval_agent_cases.yaml"


def deepeval_available() -> bool:
    try:
        import deepeval  # noqa: F401

        return True
    except ImportError:
        return False


def _load_cases() -> list[dict[str, Any]]:
    if not _FIXTURES.is_file():
        return []
    data = yaml.safe_load(_FIXTURES.read_text(encoding="utf-8")) or {}
    return list(data.get("cases") or [])


def _score_trajectory_case(case: dict[str, Any]) -> float:
    actual = set(case.get("actual_trajectory_tools") or case.get("trajectory_tools") or [])
    expected = set(case.get("trajectory_tools") or [])
    forbidden = set(case.get("forbidden_tools") or [])
    if actual & forbidden:
        return 0.0
    if expected and not expected.issubset(actual):
        return len(actual & expected) / len(expected)
    return 1.0


def run_deterministic(*, warn_only: bool = False) -> tuple[bool, dict[str, Any]]:
    cases = _load_cases()
    if not cases:
        return True, {"mode": "deterministic", "skipped": True, "reason": "no fixtures"}

    threshold = float_env("BUTLER_EVAL_DEEPEVAL_PASS_RATE_MIN", 1.0)
    scores: list[float] = []
    details: list[dict[str, Any]] = []

    for case in cases:
        score = _score_trajectory_case(case)
        case_min = float(case.get("min_score", 1.0))
        passed = score >= case_min
        scores.append(score if passed else 0.0)
        details.append({"id": case.get("id"), "score": score, "passed": passed})

    pass_rate = sum(1 for d in details if d["passed"]) / len(cases) if cases else 0.0
    ok = all(d["passed"] for d in details) or warn_only
    return ok, {
        "mode": "deterministic",
        "pass_rate": round(pass_rate, 4),
        "threshold": threshold,
        "cases_total": len(cases),
        "cases_passed": sum(1 for d in details if d["passed"]),
        "details": details,
        "deepeval_installed": deepeval_available(),
    }


def _llm_configured() -> bool:
    import os

    if os.environ.get("BUTLER_EVAL_DEEPEVAL_LLM", "").strip() in ("1", "true", "yes"):
        return True
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "BUTLER_LLM_API_KEY"):
        if os.environ.get(key, "").strip():
            return True
    return False


def run_llm_pilot(*, warn_only: bool = False) -> tuple[bool, dict[str, Any]]:
    """Optional LLM-backed relevancy on first fixture (opt-in)."""
    if not deepeval_available() or not _llm_configured():
        return run_deterministic(warn_only=warn_only)

    cases = _load_cases()
    if not cases:
        return run_deterministic(warn_only=warn_only)

    try:
        from deepeval import assert_test
        from deepeval.metrics import AnswerRelevancyMetric
        from deepeval.test_case import LLMTestCase
    except ImportError:
        return run_deterministic(warn_only=warn_only)

    threshold = float_env("BUTLER_EVAL_DEEPEVAL_PASS_RATE_MIN", 0.8)
    case = cases[0]
    user_input = str(case.get("user_input", ""))
    metric = AnswerRelevancyMetric(threshold=threshold)
    test_case = LLMTestCase(
        input=user_input,
        actual_output=f"Invoked tools: {', '.join(case.get('trajectory_tools') or []) or 'none'}",
    )
    try:
        assert_test(test_case, [metric])
        return True, {
            "mode": "llm_pilot",
            "pass_rate": 1.0,
            "threshold": threshold,
            "pilot_case": case.get("id"),
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


def run_deepeval_agent(*, warn_only: bool = False) -> tuple[bool, dict[str, Any]]:
    if not deepeval_available():
        return True, {"skipped": True, "reason": "deepeval not installed"}
    if _llm_configured():
        return run_llm_pilot(warn_only=warn_only)
    return run_deterministic(warn_only=warn_only)
