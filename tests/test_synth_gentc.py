"""Tests for CD8 Synth (code synthesizer) and CD6 GenTC (test generation)."""

from __future__ import annotations

import pytest

from butler.dev_engine.coding_knowledge import (
    CodingElement,
    ExperienceLibrary,
    TheoremLibrary,
    generate_test_cases,
    process_task,
    synthesize,
)


@pytest.fixture
def libs():
    tl = TheoremLibrary()
    el = ExperienceLibrary(theorem_lib=tl)
    return tl, el


class TestSynthesize:
    def test_basic_synthesis(self, libs):
        tl, el = libs
        ctx = process_task(["loop", "while"], tl, el)
        result = synthesize(ctx)
        assert len(result.constraints) > 0
        assert "T04" in result.activated_theorem_ids

    def test_error_handling_template(self, libs):
        tl, el = libs
        ctx = process_task(["try", "exception"], tl, el)
        result = synthesize(ctx)
        assert "try:" in result.template_hint
        assert any(c.source == "T06" for c in result.constraints)

    def test_boundary_template(self, libs):
        tl, el = libs
        ctx = process_task(["api", "file"], tl, el)
        result = synthesize(ctx)
        assert "with" in result.template_hint or "resource" in result.template_hint

    def test_must_not_constraints(self, libs):
        tl, el = libs
        ctx = process_task(["pure", "deterministic"], tl, el)
        result = synthesize(ctx)
        must_nots = [c for c in result.constraints if c.category == "must_not"]
        assert len(must_nots) > 0

    def test_summary(self, libs):
        tl, el = libs
        ctx = process_task(["loop"], tl, el)
        result = synthesize(ctx)
        assert result.summary
        assert "MUST" in result.summary or "no constraints" in result.summary

    def test_experience_guided_synthesis(self, libs):
        from butler.dev_engine.coding_knowledge import CodingExperience
        tl, el = libs
        exp = CodingExperience(
            id="EXP_TEST",
            title="test pattern",
            domain=["loop"],
            theorem_basis={"T04"},
            context="loop optimization pattern",
            pattern="for i in range(n):\n    process(i)\n",
        )
        el.add(exp, skip_validation=True)
        ctx = process_task(["loop"], tl, el)
        result = synthesize(ctx)
        if ctx.selected_experience:
            assert result.experience_pattern
            assert any(c.category == "prefer" for c in result.constraints)

    def test_empty_context(self, libs):
        tl, el = libs
        ctx = process_task(["zzz_unknown"], tl, el)
        result = synthesize(ctx)
        assert isinstance(result.constraints, list)


class TestGenTC:
    def test_basic_generation(self, libs):
        tl, el = libs
        ctx = process_task(["loop", "exception"], tl, el)
        result = generate_test_cases(ctx)
        assert result.count > 0
        assert len(result.coverage_classes) > 0

    def test_error_handling_cases(self, libs):
        tl, el = libs
        ctx = process_task(["try", "exception", "error"], tl, el)
        result = generate_test_cases(ctx)
        cats = result.category_breakdown
        assert "error" in cats or "normal" in cats

    def test_boundary_cases(self, libs):
        tl, el = libs
        ctx = process_task(["loop", "while", "for"], tl, el)
        result = generate_test_cases(ctx)
        cats = result.category_breakdown
        assert "boundary" in cats

    def test_input_validation_cases(self, libs):
        tl, el = libs
        ctx = process_task(["input", "validate", "external"], tl, el)
        result = generate_test_cases(ctx)
        assert any(tc.category == "negative" for tc in result.test_cases)

    def test_element_coverage(self, libs):
        tl, el = libs
        ctx = process_task(["api", "error", "loop"], tl, el)
        result = generate_test_cases(ctx)
        element_cases = [tc for tc in result.test_cases if tc.id.startswith("ELEM_")]
        assert len(element_cases) > 0

    def test_all_theorems_coverage(self, libs):
        tl, el = libs
        all_keywords = [
            "pure", "compose", "type", "loop", "state",
            "exception", "idempotent", "open", "api", "input",
        ]
        ctx = process_task(all_keywords, tl, el)
        result = generate_test_cases(ctx)
        theorem_ids = {tc.theorem_source for tc in result.test_cases if tc.theorem_source}
        assert len(theorem_ids) >= 5

    def test_empty_context_returns_baseline(self, libs):
        tl, el = libs
        ctx = process_task(["zzz_unknown"], tl, el)
        result = generate_test_cases(ctx)
        assert isinstance(result.test_cases, list)


class TestEndToEndKnowledgePipeline:
    def test_process_then_synth_then_gentc(self, libs):
        tl, el = libs
        ctx = process_task(["api", "error", "validate"], tl, el)
        synth = synthesize(ctx)
        tests = generate_test_cases(ctx)

        assert synth.constraints
        assert tests.count > 0
        for tid in synth.activated_theorem_ids:
            if tid in {"T06", "T09", "T10"}:
                assert any(tc.theorem_source == tid for tc in tests.test_cases)
