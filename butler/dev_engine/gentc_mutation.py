"""P-CT4a / H10: GenTC equivalence-class audit + lightweight mutation score.

Validates that CD6 GenTC patterns cover declared equivalence classes and that
instantiated oracle predicates kill a minimum fraction of simple code mutants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from butler.dev_engine.coding_knowledge import (
    CodingKnowledgeContext,
    GenTCResult,
    TestCase,
    _THEOREM_TEST_PATTERNS,
    generate_test_cases,
)

Predicate = Callable[[dict[str, Any]], bool]


def default_mutation_min_score() -> float:
    raw = os.getenv("BUTLER_GENTC_MUTATION_MIN_SCORE", "0.6").strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.6


@dataclass
class CoverageAuditResult:
    passed: bool
    missing: list[str] = field(default_factory=list)


@dataclass
class MutationScoreResult:
    total_mutants: int
    killed: int
    score: float
    unkilled_ids: list[str] = field(default_factory=list)
    theorem_id: str = ""

    @property
    def passed(self) -> bool:
        return self.score >= default_mutation_min_score()


@dataclass
class PCT4aEvaluation:
    coverage: CoverageAuditResult
    mutation_scores: list[MutationScoreResult]
    min_score: float

    @property
    def average_mutation_score(self) -> float:
        if not self.mutation_scores:
            return 1.0
        return sum(m.score for m in self.mutation_scores) / len(self.mutation_scores)

    @property
    def passed(self) -> bool:
        if not self.coverage.passed:
            return False
        if not self.mutation_scores:
            return True
        return all(m.score >= self.min_score for m in self.mutation_scores)


@dataclass(frozen=True)
class MutationSpecimen:
    theorem_id: str
    correct_code: str
    mutants: tuple[str, ...]
    predicates: tuple[tuple[str, Predicate], ...]


def _exec_snippet(code: str) -> dict[str, Any]:
    ns: dict[str, Any] = {}
    exec(code, {"__builtins__": __builtins__}, ns)
    return ns


def audit_equivalence_class_coverage(
    result: GenTCResult,
    activated_theorem_ids: Iterable[str],
) -> CoverageAuditResult:
    """P-CT4a structural check: GenTC includes all pattern categories per theorem."""
    missing: list[str] = []
    for tid in sorted(set(activated_theorem_ids)):
        patterns = _THEOREM_TEST_PATTERNS.get(tid, [])
        if not patterns:
            continue
        required = {p.category for p in patterns}
        actual = {
            tc.category
            for tc in result.test_cases
            if tc.theorem_source == tid
        }
        gap = required - actual
        if gap:
            missing.append(f"{tid}: missing {sorted(gap)}")
    return CoverageAuditResult(passed=not missing, missing=missing)


def mutation_score(
    specimen: MutationSpecimen,
    *,
    min_score: float | None = None,
) -> MutationScoreResult:
    """Fraction of mutants detected by at least one failing predicate."""
    _ = min_score  # threshold checked by caller / PCT4aEvaluation
    good_ns = _exec_snippet(specimen.correct_code)
    for name, pred in specimen.predicates:
        if not pred(good_ns):
            raise ValueError(f"predicate {name!r} fails on correct code for {specimen.theorem_id}")

    killed = 0
    unkilled: list[str] = []
    for idx, mutant_code in enumerate(specimen.mutants):
        mid = f"{specimen.theorem_id}_mut{idx}"
        from butler.dev_engine.gentc_mutation_ops import exec_mutant_snippet_safe, mutant_detected_safe

        m_ns, exec_failed = exec_mutant_snippet_safe(mutant_code, _exec_snippet)
        if exec_failed:
            killed += 1
            continue
        detected = mutant_detected_safe(m_ns, specimen.predicates)
        if detected:
            killed += 1
        else:
            unkilled.append(mid)

    total = len(specimen.mutants)
    score = (killed / total) if total else 1.0
    return MutationScoreResult(
        total_mutants=total,
        killed=killed,
        score=score,
        unkilled_ids=unkilled,
        theorem_id=specimen.theorem_id,
    )


# Oracle predicates embody GenTC equivalence classes (normal / boundary / error).
_MUTATION_SPECIMENS: tuple[MutationSpecimen, ...] = (
    MutationSpecimen(
        "T01",
        "def double(x):\n    return x * 2\n",
        (
            "def double(x):\n    return x * 3\n",
            "def double(x):\n    return x + 1\n",
            "def double(x):\n    return 0\n",
        ),
        (
            ("determinism", lambda ns: ns["double"](3) == ns["double"](3)),
            ("normal", lambda ns: ns["double"](2) == 4),
            ("boundary_none", lambda ns: ns["double"](0) == 0),
        ),
    ),
    MutationSpecimen(
        "T04",
        "def sum_list(xs):\n    total = 0\n    for x in xs:\n        total += x\n    return total\n",
        (
            "def sum_list(xs):\n    return 1\n",
            "def sum_list(xs):\n    total = 0\n    for x in xs:\n        total += x + 1\n    return total\n",
            "def sum_list(xs):\n    return len(xs)\n",
        ),
        (
            ("normal", lambda ns: ns["sum_list"]([1, 2, 3]) == 6),
            ("boundary_empty", lambda ns: ns["sum_list"]([]) == 0),
            ("boundary_large", lambda ns: ns["sum_list"](list(range(50))) == 1225),
        ),
    ),
    MutationSpecimen(
        "T06",
        "def safe_div(a, b):\n    try:\n        return a / b\n    except ZeroDivisionError:\n        return None\n",
        (
            "def safe_div(a, b):\n    return a / b\n",
            "def safe_div(a, b):\n    try:\n        return a + b\n    except ZeroDivisionError:\n        return None\n",
            "def safe_div(a, b):\n    return 0\n",
        ),
        (
            ("normal", lambda ns: ns["safe_div"](10, 2) == 5),
            ("error", lambda ns: ns["safe_div"](1, 0) is None),
            ("boundary", lambda ns: ns["safe_div"](0, 5) == 0),
        ),
    ),
    MutationSpecimen(
        "T07",
        "def upsert(d, key, value):\n    d[key] = value\n    return d.get(key)\n",
        (
            "def upsert(d, key, value):\n    d[key] = value\n    d[key] = value + '_x'\n    return d.get(key)\n",
            "def upsert(d, key, value):\n    d.setdefault(key, [])\n    d[key].append(value)\n    return d.get(key)\n",
            "def upsert(d, key, value):\n    return None\n",
        ),
        (
            ("normal", lambda ns: ns["upsert"]({}, "a", 2) == 2),
            ("idempotent", lambda ns: ns["upsert"]({"k": 1}, "k", 1) == 1),
        ),
    ),
    MutationSpecimen(
        "T10",
        "def sanitize(text):\n    if not text:\n        return ''\n    if '<' in text or '>' in text:\n        raise ValueError('invalid')\n    return text.strip()\n",
        (
            "def sanitize(text):\n    return text\n",
            "def sanitize(text):\n    return text.upper()\n",
            "def sanitize(text):\n    if not text:\n        return 'x'\n    return text\n",
        ),
        (
            ("normal", lambda ns: ns["sanitize"](' hello ') == 'hello'),
            ("negative", lambda ns: _raises_value_error(ns["sanitize"], '<bad>')),
            ("boundary_empty", lambda ns: ns["sanitize"]('') == ''),
        ),
    ),
)


def _raises_value_error(fn: Callable[..., Any], *args: Any) -> bool:
    try:
        fn(*args)
    except ValueError:
        return True
    return False


def specimens_for_theorems(theorem_ids: Iterable[str]) -> list[MutationSpecimen]:
    wanted = set(theorem_ids)
    return [s for s in _MUTATION_SPECIMENS if s.theorem_id in wanted]


def evaluate_pct4a(
    ctx: CodingKnowledgeContext,
    *,
    min_score: float | None = None,
) -> PCT4aEvaluation:
    """Full P-CT4a premise check for a coding knowledge context."""
    threshold = default_mutation_min_score() if min_score is None else min_score
    gentc = generate_test_cases(ctx)
    coverage = audit_equivalence_class_coverage(
        gentc, ctx.activated_theorems.keys()
    )
    scores: list[MutationScoreResult] = []
    for spec in specimens_for_theorems(ctx.activated_theorems.keys()):
        scores.append(mutation_score(spec))
    return PCT4aEvaluation(
        coverage=coverage,
        mutation_scores=scores,
        min_score=threshold,
    )


def categories_for_theorem(tid: str) -> set[str]:
    """Expose pattern categories for tests."""
    return {p.category for p in _THEOREM_TEST_PATTERNS.get(tid, [])}


__all__ = [
    "CoverageAuditResult",
    "MutationScoreResult",
    "MutationSpecimen",
    "PCT4aEvaluation",
    "audit_equivalence_class_coverage",
    "categories_for_theorem",
    "default_mutation_min_score",
    "evaluate_pct4a",
    "mutation_score",
    "specimens_for_theorems",
]
