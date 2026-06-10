"""P-CT4a / H10: GenTC equivalence-class coverage + mutation score."""

from __future__ import annotations

import pytest

from butler.dev_engine.coding_knowledge import (
    ExperienceLibrary,
    TheoremLibrary,
    generate_test_cases,
    process_task,
)
from butler.dev_engine.gentc_mutation import (
    MutationSpecimen,
    audit_equivalence_class_coverage,
    categories_for_theorem,
    evaluate_pct4a,
    mutation_score,
    specimens_for_theorems,
)


@pytest.fixture
def libs():
    return TheoremLibrary(), ExperienceLibrary(theorem_lib=TheoremLibrary())


class TestPCT4aEquivalenceCoverage:
    def test_gentc_covers_all_pattern_categories(self, libs) -> None:
        tl, el = libs
        keywords = [
            "pure", "compose", "type", "loop", "state",
            "exception", "idempotent", "open", "api", "input",
        ]
        ctx = process_task(keywords, tl, el)
        gentc = generate_test_cases(ctx)
        audit = audit_equivalence_class_coverage(
            gentc, ctx.activated_theorems.keys()
        )
        assert audit.passed, audit.missing

    def test_audit_detects_missing_category(self, libs) -> None:
        tl, el = libs
        ctx = process_task(["loop", "exception"], tl, el)
        gentc = generate_test_cases(ctx)
        # Drop error-class cases to simulate under-coverage.
        trimmed = type(gentc)(
            test_cases=[tc for tc in gentc.test_cases if tc.category != "error"],
            coverage_classes=gentc.coverage_classes,
        )
        audit = audit_equivalence_class_coverage(
            trimmed, {"T06"}
        )
        assert not audit.passed
        assert any("T06" in line for line in audit.missing)


class TestPCT4aMutationScore:
    def test_specimen_kills_majority_of_mutants(self) -> None:
        specs = specimens_for_theorems(["T01", "T04", "T06", "T07", "T10"])
        assert len(specs) == 5
        for spec in specs:
            result = mutation_score(spec)
            assert result.killed >= 2, (
                f"{spec.theorem_id}: score={result.score}, unkilled={result.unkilled_ids}"
            )
            assert result.score >= 0.6

    def test_weak_predicates_fail_mutation_gate(self) -> None:
        weak = MutationSpecimen(
            "T01",
            "def double(x):\n    return x * 2\n",
            ("def double(x):\n    return x * 3\n",),
            (("trivial", lambda ns: callable(ns["double"])),),
        )
        result = mutation_score(weak)
        assert result.killed == 0
        assert result.score == 0.0

    def test_t06_error_class_maps_to_zero_division(self) -> None:
        assert "error" in categories_for_theorem("T06")


class TestPCT4aEvaluation:
    def test_evaluate_pct4a_passes_representative_context(self, libs) -> None:
        tl, el = libs
        ctx = process_task(
            ["pure", "loop", "exception", "idempotent", "api", "input"],
            tl,
            el,
        )
        evaluation = evaluate_pct4a(ctx, min_score=0.6)
        assert evaluation.coverage.passed
        assert evaluation.mutation_scores
        assert evaluation.passed
        assert evaluation.average_mutation_score >= 0.6

    def test_evaluate_pct4a_respects_min_score_env(self, libs, monkeypatch) -> None:
        tl, el = libs
        ctx = process_task(["pure", "loop"], tl, el)
        monkeypatch.setenv("BUTLER_GENTC_MUTATION_MIN_SCORE", "0.99")
        evaluation = evaluate_pct4a(ctx)
        assert evaluation.min_score == 0.99
