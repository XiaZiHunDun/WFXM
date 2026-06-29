"""RAGAS memory faithfulness pilot — heuristic overlap + optional LLM."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from butler.env_parse import float_env

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ragas_memory_cases.yaml"


def ragas_available() -> bool:
    try:
        import ragas  # noqa: F401

        return True
    except ImportError:
        return False


def _load_cases() -> list[dict[str, Any]]:
    from butler.eval_integration.oss.prefetch_audit_loader import load_prefetch_audit_cases

    audit = load_prefetch_audit_cases()
    if audit:
        return audit
    if not _FIXTURES.is_file():
        return []
    data = yaml.safe_load(_FIXTURES.read_text(encoding="utf-8")) or {}
    return list(data.get("cases") or [])


def _tokenize(text: str) -> set[str]:
    parts = re.findall(r"[\w/.-]+", text.lower())
    return {p for p in parts if len(p) >= 3}


def heuristic_faithfulness(context: str, answer: str) -> float:
    """Context–answer token overlap ratio (0–1), no LLM."""
    ctx_tokens = _tokenize(context)
    if not ctx_tokens:
        return 0.0
    ans_tokens = _tokenize(answer)
    if not ans_tokens:
        return 0.0
    overlap = len(ctx_tokens & ans_tokens)
    return overlap / len(ctx_tokens)


def run_heuristic(*, warn_only: bool = False) -> tuple[bool, dict[str, Any]]:
    cases = _load_cases()
    if not cases:
        return True, {"mode": "heuristic", "skipped": True, "reason": "no fixtures"}

    threshold = float_env("BUTLER_EVAL_RAGAS_FAITHFULNESS_MIN", 0.5)
    details: list[dict[str, Any]] = []

    for case in cases:
        ctx = str(case.get("context", ""))
        ans = str(case.get("answer", ""))
        score = heuristic_faithfulness(ctx, ans)
        min_f = case.get("min_faithfulness")
        max_f = case.get("max_faithfulness")
        passed = True
        if min_f is not None and score < float(min_f):
            passed = False
        if max_f is not None and score > float(max_f):
            passed = False
        details.append(
            {
                "id": case.get("id"),
                "faithfulness": round(score, 4),
                "passed": passed,
            }
        )

    avg = sum(s for s in [heuristic_faithfulness(str(c.get("context", "")), str(c.get("answer", ""))) for c in cases]) / len(cases) if cases else 0.0
    cases_passed = sum(1 for d in details if d["passed"])
    ok = cases_passed == len(cases) or warn_only
    mode = "audit" if any(c.get("source") == "transcript_audit" for c in cases) else "heuristic"
    return ok, {
        "mode": mode,
        "faithfulness_avg": round(avg, 4),
        "threshold": threshold,
        "cases_total": len(cases),
        "cases_passed": cases_passed,
        "details": details,
        "ragas_installed": ragas_available(),
    }


def _llm_configured() -> bool:
    import os

    if os.environ.get("BUTLER_EVAL_RAGAS_LLM", "").strip() in ("1", "true", "yes"):
        return True
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "BUTLER_LLM_API_KEY"):
        if os.environ.get(key, "").strip():
            return True
    return False


def run_ragas_memory(*, warn_only: bool = False) -> tuple[bool, dict[str, Any]]:
    if not ragas_available():
        return True, {"skipped": True, "reason": "ragas not installed"}
    # Pilot: heuristic even when ragas installed (LLM path deferred)
    return run_heuristic(warn_only=warn_only)
