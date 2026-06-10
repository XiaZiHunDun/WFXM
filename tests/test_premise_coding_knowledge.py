"""Premise verification tests for Coding Knowledge Layer (Chapter 9 v1.4).

Validates axioms CA1-CA4, definitions CD0-CD8, theorems CT1-CT5,
lemma CL1, and hypotheses H0-H13.

Reference: docs/architecture/v4-dev-engine-theory.md Chapter 9
"""

from __future__ import annotations

import time
from typing import Dict, Set

import pytest

from butler.dev_engine.coding_knowledge import (
    BASELINE_THEOREMS,
    CodingElement,
    CodingExperience,
    CodingKnowledgeContext,
    CodingTheorem,
    DualVerificationResult,
    ELEMENT_THEOREM_MAP,
    ELEMENT_VERIFICATION_PROPERTIES,
    ExperienceLibrary,
    TheoremCheckResult,
    TheoremLibrary,
    build_default_theorem_library,
    decompose_task,
    dual_verify,
    process_task,
    verify_theorems,
)


# ═══════════════════════════════════════════════════════════════════
# P-CA1: Coding Element Composable Coverage
# ═══════════════════════════════════════════════════════════════════

class TestCA1CodingElements:

    def test_pca1a_exactly_seven_elements(self) -> None:
        assert len(CodingElement) == 7

    def test_pca1b_elements_have_distinct_verification_properties(self) -> None:
        all_props: list[list[str]] = []
        for elem in CodingElement:
            props = ELEMENT_VERIFICATION_PROPERTIES[elem]
            assert len(props) >= 2, f"{elem} needs ≥2 verification properties"
            all_props.append(props)
        for i, props_i in enumerate(all_props):
            for j, props_j in enumerate(all_props):
                if i != j:
                    overlap = set(props_i) & set(props_j)
                    assert not overlap

    def test_pca1c_simple_task_decomposes(self) -> None:
        elements = decompose_task(["filter", "map"])
        assert CodingElement.DATA_FLOW in elements
        assert CodingElement.CONTROL_FLOW in elements

    def test_pca1d_complex_task_decomposes(self) -> None:
        elements = decompose_task(["cache", "exception", "type", "fetch"])
        assert CodingElement.STATE_MANAGEMENT in elements
        assert CodingElement.ERROR_HANDLING in elements
        assert CodingElement.TYPE_SCHEMA in elements
        assert CodingElement.BOUNDARY_INTERFACE in elements

    def test_pca1e_empty_keywords_yield_empty_elements(self) -> None:
        assert len(decompose_task([])) == 0

    def test_pca1f_all_elements_reachable(self) -> None:
        all_kws = ["transform", "loop", "store", "compose",
                    "api", "exception", "type"]
        assert len(decompose_task(all_kws)) == 7

    def test_pca1g_interface_maps_to_both_elements(self) -> None:
        """interface keyword maps to TypeSchema AND BoundaryInterface."""
        elements = decompose_task(["interface"])
        assert CodingElement.TYPE_SCHEMA in elements
        assert CodingElement.BOUNDARY_INTERFACE in elements

    def test_pca1h_every_element_has_theorem_mapping(self) -> None:
        for elem in CodingElement:
            assert elem in ELEMENT_THEOREM_MAP
            assert len(ELEMENT_THEOREM_MAP[elem]) >= 1


# ═══════════════════════════════════════════════════════════════════
# P-CA2: Theorem Semantic Invariance
# ═══════════════════════════════════════════════════════════════════

class TestCA2TheoremInvariance:

    def test_pca2a_default_library_has_10_theorems(self) -> None:
        assert len(TheoremLibrary().theorems) == 10

    def test_pca2b_three_layers_covered(self) -> None:
        layers = {t.layer for t in TheoremLibrary().theorems.values()}
        assert layers == {"computation", "effect_state", "resource_boundary"}

    def test_pca2c_computation_layer_ids(self) -> None:
        comp = [t for t in TheoremLibrary().theorems.values()
                if t.layer == "computation"]
        assert {t.id for t in comp} == {"T01", "T02", "T03", "T04"}

    def test_pca2d_effect_state_layer_ids(self) -> None:
        eff = [t for t in TheoremLibrary().theorems.values()
               if t.layer == "effect_state"]
        assert {t.id for t in eff} == {"T05", "T06", "T07"}

    def test_pca2e_resource_layer_ids(self) -> None:
        res = [t for t in TheoremLibrary().theorems.values()
               if t.layer == "resource_boundary"]
        assert {t.id for t in res} == {"T08", "T09", "T10"}

    def test_pca2f_every_theorem_has_triggers(self) -> None:
        for tid, t in TheoremLibrary().theorems.items():
            assert len(t.triggers) > 0, f"{tid} has no triggers"

    def test_pca2g_theorem_ids_sequential(self) -> None:
        assert TheoremLibrary().all_ids() == {f"T{i:02d}" for i in range(1, 11)}

    def test_pca2h_every_theorem_has_checker(self) -> None:
        lib = TheoremLibrary()
        for t in lib.theorems.values():
            result = t.check("x = 1")
            assert isinstance(result, TheoremCheckResult)

    def test_pca2i_every_theorem_has_element_triggers(self) -> None:
        lib = TheoremLibrary()
        for tid, t in lib.theorems.items():
            assert len(t.element_triggers) > 0, \
                f"{tid} has no element_triggers"


# ═══════════════════════════════════════════════════════════════════
# P-CA3: Experience Accuracy (CA3a + CA3b)
# ═══════════════════════════════════════════════════════════════════

class TestCA3ExperienceAccuracy:

    def _make_exp(self, valid_start=0.0, valid_end=float("inf"),
                  theorem_basis=None) -> CodingExperience:
        return CodingExperience(
            id="E001", title="Test experience",
            domain=["Python", "caching"],
            theorem_basis=theorem_basis or {"T05", "T06"},
            context="caching with expiry",
            pattern="def with_cache(fn, ttl): pass",
            validity_start=valid_start, validity_end=valid_end,
        )

    def test_pca3a_valid_experience_is_valid(self) -> None:
        assert self._make_exp().is_valid()

    def test_pca3b_expired_experience_is_invalid(self) -> None:
        assert not self._make_exp(100, 200).is_valid(now=300)

    def test_pca3c_future_experience_is_invalid(self) -> None:
        assert not self._make_exp(9999999990, 9999999999).is_valid(now=100)

    def test_pca3d_default_validity_is_infinite(self) -> None:
        exp = CodingExperience(
            id="X", title="X", domain=[], theorem_basis=set(),
            context="x", pattern="x",
        )
        assert exp.is_valid()

    def test_pca3e_covers_subset(self) -> None:
        exp = self._make_exp(theorem_basis={"T05", "T06", "T08"})
        assert exp.covers_theorems({"T05", "T06"})
        assert not exp.covers_theorems({"T05", "T10"})

    def test_pca3f_boundary_validity_at_endpoints(self) -> None:
        exp = self._make_exp(100.0, 200.0)
        assert exp.is_valid(now=100.0)
        assert exp.is_valid(now=200.0)
        assert not exp.is_valid(now=99.9)
        assert not exp.is_valid(now=200.1)


# ═══════════════════════════════════════════════════════════════════
# P-CA4: Dual Verification Closure (Strict Mode)
# ═══════════════════════════════════════════════════════════════════

class TestCA4DualVerification:

    def _activated(self) -> Dict[str, CodingTheorem]:
        lib = TheoremLibrary()
        return {"T05": lib.get("T05"), "T06": lib.get("T06")}

    def test_pca4a_both_pass_yields_output(self) -> None:
        result = dual_verify("def f(x): return x + 1",
                             self._activated(), test_passed=True)
        assert result.all_passed

    def test_pca4b_theorem_fail_blocks_output(self) -> None:
        result = dual_verify("global x\nx = 1",
                             self._activated(), test_passed=True)
        assert not result.all_passed
        assert "T05" in result.violated_theorems

    def test_pca4c_test_fail_blocks_output(self) -> None:
        result = dual_verify("def f(x): return x + 1",
                             self._activated(), test_passed=False)
        assert not result.all_passed
        assert result.theorem_passed

    def test_pca4d_both_fail_blocks_output(self) -> None:
        result = dual_verify("global x\nx = 1",
                             self._activated(), test_passed=False)
        assert not result.all_passed

    def test_pca4e_empty_activation_blocks_theorem_gate(self) -> None:
        """Empty activation set → theorem_passed=False (no vacuous truth)."""
        result = dual_verify("def f(): pass", {}, test_passed=True)
        assert not result.theorem_passed
        assert not result.all_passed


# ═══════════════════════════════════════════════════════════════════
# P-CT1: Verified Program Compliance — ALL 10 theorems
# ═══════════════════════════════════════════════════════════════════

class TestCT1TheoremCompliance:

    def _check_one(self, tid: str, code: str) -> TheoremCheckResult:
        lib = TheoremLibrary()
        t = lib.get(tid)
        return t.check(code)

    # --- T01 Determinism ---
    def test_t01_pass_pure_function(self) -> None:
        assert self._check_one("T01", "def f(x): return x * 2").passed

    def test_t01_fail_random(self) -> None:
        assert not self._check_one("T01", "import random\nx = random.randint(1,10)").passed

    def test_t01_fail_datetime(self) -> None:
        assert not self._check_one("T01", "from datetime import datetime\nt = datetime.now()").passed

    # --- T02 Composability ---
    def test_t02_pass(self) -> None:
        assert self._check_one("T02", "g(f(x))").passed

    # --- T03 Type Safety ---
    def test_t03_pass_isinstance(self) -> None:
        assert self._check_one("T03", "if isinstance(x, int): y = x + 1").passed

    def test_t03_fail_eval(self) -> None:
        assert not self._check_one("T03", "result = eval(user_input)").passed

    # --- T04 Termination ---
    def test_t04_pass_bounded_loop(self) -> None:
        assert self._check_one("T04", "for i in range(10): pass").passed

    def test_t04_fail_infinite_loop(self) -> None:
        assert not self._check_one("T04", "while True:\n    do_work()").passed

    def test_t04_pass_while_true_with_break(self) -> None:
        assert self._check_one("T04", "while True:\n    if done: break").passed

    # --- T05 State Isolation ---
    def test_t05_pass_local_state(self) -> None:
        assert self._check_one("T05", "def f(): _local = 1; return _local").passed

    def test_t05_fail_global(self) -> None:
        assert not self._check_one("T05", "global shared_state\nshared_state = {}").passed

    # --- T06 Exception Safety ---
    def test_t06_pass_try_except(self) -> None:
        assert self._check_one("T06", "try:\n    x()\nexcept Exception:\n    pass").passed

    def test_t06_fail_try_without_except(self) -> None:
        assert not self._check_one("T06", "try:\n    do_something()").passed

    def test_t06_fail_bare_except_pass(self) -> None:
        assert not self._check_one("T06", "try:\n    x()\nexcept: pass").passed

    # --- T07 Idempotency ---
    def test_t07_pass_simple(self) -> None:
        assert self._check_one("T07", "def f(x): return abs(x)").passed

    # --- T08 Resource Lifecycle ---
    def test_t08_pass_with_statement(self) -> None:
        assert self._check_one("T08", "with open('f') as f:\n    data = f.read()").passed

    def test_t08_fail_open_no_close(self) -> None:
        assert not self._check_one("T08", "f = open('test.txt')\ndata = f.read()").passed

    def test_t08_pass_try_finally(self) -> None:
        assert self._check_one("T08", "f = open('x')\ntry:\n    pass\nfinally:\n    f.close()").passed

    # --- T09 Contract Adherence ---
    def test_t09_pass_status_check(self) -> None:
        code = "r = requests.get(url)\nr.raise_for_status()"
        assert self._check_one("T09", code).passed

    def test_t09_fail_no_status_check(self) -> None:
        code = "r = requests.get(url)\ndata = r.json()"
        assert not self._check_one("T09", code).passed

    # --- T10 Trust Boundary ---
    def test_t10_pass_validated_input(self) -> None:
        code = "x = input('num: ')\nval = int(x)"
        assert self._check_one("T10", code).passed

    def test_t10_fail_raw_input(self) -> None:
        code = "x = input('cmd: ')\nos.system(x)"
        assert not self._check_one("T10", code).passed


# ═══════════════════════════════════════════════════════════════════
# CL1: Composition Closure (limited scope)
# ═══════════════════════════════════════════════════════════════════

class TestCL1CompositionClosure:

    def _verify(self, code: str, tids: list[str]) -> list[TheoremCheckResult]:
        lib = TheoremLibrary()
        activated = {tid: lib.get(tid) for tid in tids}
        return verify_theorems(code, activated)

    def test_cl1_t05_concat_preserves(self) -> None:
        code = "def a(): _a = 1; return _a\ndef b(): _b = 2; return _b"
        assert all(r.passed for r in self._verify(code, ["T05"]))

    def test_cl1_t06_nesting_preserves(self) -> None:
        code = ("def outer():\n    try:\n        def inner():\n"
                "            try:\n                x = risky()\n"
                "            except ValueError:\n                pass\n"
                "        inner()\n    except Exception:\n        pass")
        assert all(r.passed for r in self._verify(code, ["T06"]))

    def test_cl1_t08_multiple_with_preserves(self) -> None:
        code = ("with open('a') as f1:\n    d1 = f1.read()\n"
                "with open('b') as f2:\n    d2 = f2.read()")
        assert all(r.passed for r in self._verify(code, ["T08"]))

    def test_cl1_negative_global_in_concat_fails_t05(self) -> None:
        """Composing a compliant and a non-compliant fragment should fail."""
        code = "def a(): _a = 1; return _a\nglobal shared\nshared = {}"
        results = self._verify(code, ["T05"])
        assert any(not r.passed for r in results)

    def test_cl1_negative_open_without_close_in_nesting(self) -> None:
        code = ("with open('a') as f1:\n    d1 = f1.read()\n"
                "f2 = open('b')\nd2 = f2.read()")
        results = self._verify(code, ["T08"])
        assert any(not r.passed for r in results)


# ═══════════════════════════════════════════════════════════════════
# P-CT2: Graceful Degradation (end-to-end)
# ═══════════════════════════════════════════════════════════════════

class TestCT2GracefulDegradation:

    def test_pct2a_empty_lib_yields_theorem_only(self) -> None:
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary()
        ctx = process_task(["cache", "exception"], tlib, xlib)
        assert ctx.mode == "theorem_only"
        assert ctx.selected_experience is None
        assert len(ctx.activated_theorems) > 0

    def test_pct2b_expired_experience_excluded(self) -> None:
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary()
        xlib.add(CodingExperience(
            id="E_old", title="Old", domain=["caching"],
            theorem_basis={"T05"}, context="cache", pattern="pass",
            validity_start=100, validity_end=200,
        ), skip_validation=True)
        ctx = process_task(["cache"], tlib, xlib, now=300)
        assert ctx.mode == "theorem_only"

    def test_pct2c_theorem_only_still_has_constraints(self) -> None:
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary()
        ctx = process_task(["cache", "state", "exception"], tlib, xlib)
        assert "T05" in ctx.activated_theorems
        assert "T06" in ctx.activated_theorems

    def test_pct2d_degraded_code_passes_theorem_verification(self) -> None:
        """End-to-end: theorem_only mode → clean code → verify passes."""
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary()
        ctx = process_task(["cache", "exception"], tlib, xlib)
        code = ("def with_cache(fn):\n    _cache = {}\n"
                "    def wrapper(*a):\n        try:\n"
                "            return fn(*a)\n"
                "        except Exception as e:\n"
                "            raise e\n    return wrapper")
        result = dual_verify(code, ctx.activated_theorems, test_passed=True)
        assert result.theorem_passed


# ═══════════════════════════════════════════════════════════════════
# P-CT3: Experience Update Safety (end-to-end)
# ═══════════════════════════════════════════════════════════════════

class TestCT3ExperienceUpdateSafety:

    def test_pct3a_replace_updates_library(self) -> None:
        xlib = ExperienceLibrary()
        old = CodingExperience(
            id="E001", title="Old", domain=["caching"],
            theorem_basis={"T05"}, context="cache", pattern="pass",
            validity_start=0, validity_end=float("inf"),
        )
        xlib.add(old, skip_validation=True)
        new = CodingExperience(
            id="E002", title="New", domain=["caching"],
            theorem_basis={"T05", "T06"}, context="cache", pattern="pass",
            validity_start=0, validity_end=float("inf"),
        )
        ok, _ = xlib.replace("E001", new, skip_validation=True)
        assert ok
        assert xlib.count == 1
        assert xlib.get("E001") is None
        assert xlib.get("E002") is not None
        assert xlib.get("E002").supersedes == "E001"

    def test_pct3b_replace_nonexistent_fails(self) -> None:
        xlib = ExperienceLibrary()
        new = CodingExperience(
            id="E002", title="New", domain=[], theorem_basis=set(),
            context="x", pattern="pass",
        )
        ok, detail = xlib.replace("E999", new, skip_validation=True)
        assert not ok

    def test_pct3c_add_with_validation_rejects_bad_pattern(self) -> None:
        """CT3 safety: pattern violating theorem basis is rejected."""
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary(theorem_lib=tlib)
        bad_exp = CodingExperience(
            id="E_bad", title="Bad", domain=["caching"],
            theorem_basis={"T05"},
            context="cache", pattern="global shared\nshared = {}",
        )
        ok, detail = xlib.add(bad_exp)
        assert not ok
        assert "T05" in detail

    def test_pct3d_add_with_validation_accepts_good_pattern(self) -> None:
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary(theorem_lib=tlib)
        good_exp = CodingExperience(
            id="E_good", title="Good", domain=["caching"],
            theorem_basis={"T05"},
            context="cache", pattern="def f(): _local = 1; return _local",
        )
        ok, _ = xlib.add(good_exp)
        assert ok


# ═══════════════════════════════════════════════════════════════════
# P-CT4: Test Coverage Supplement
# ═══════════════════════════════════════════════════════════════════

class TestCT4TestCoverage:

    def test_pct4a_test_fail_blocks_even_if_theorem_passes(self) -> None:
        lib = TheoremLibrary()
        activated = lib.activate(set(), set())
        result = dual_verify("def f(x): return x + 1", activated,
                             test_passed=False,
                             test_detail="assert f(1) == 3 FAILED")
        assert result.theorem_passed
        assert not result.test_passed
        assert not result.all_passed

    def test_pct4b_joint_pass(self) -> None:
        lib = TheoremLibrary()
        activated = lib.activate({"cache"}, {CodingElement.STATE_MANAGEMENT})
        result = dual_verify("def f(x):\n    _c = {}\n    return x",
                             activated, test_passed=True)
        assert result.all_passed

    def test_pct4c_failed_test_cases_recorded(self) -> None:
        result = dual_verify(
            "pass", {"T03": TheoremLibrary().get("T03")},
            test_passed=False,
            failed_test_cases=["test_add_1_1", "test_edge_zero"],
        )
        assert len(result.failed_test_cases) == 2

    def test_pct4a_gentc_mutation_premise(self) -> None:
        from butler.dev_engine.gentc_mutation import evaluate_pct4a

        tl = TheoremLibrary()
        el = ExperienceLibrary(theorem_lib=tl)
        ctx = process_task(
            ["pure", "loop", "exception", "idempotent", "api", "input"],
            tl,
            el,
        )
        assert evaluate_pct4a(ctx, min_score=0.6).passed


# ═══════════════════════════════════════════════════════════════════
# P-CT5: Joint Guarantee
# ═══════════════════════════════════════════════════════════════════

class TestCT5JointGuarantee:

    def test_pct5a_multiple_violations_listed(self) -> None:
        lib = TheoremLibrary()
        activated = {"T05": lib.get("T05"), "T08": lib.get("T08")}
        code = "global x\nf = open('a')\ndata = f.read()"
        result = dual_verify(code, activated, test_passed=True)
        assert not result.all_passed
        assert "T05" in set(result.violated_theorems)
        assert "T08" in set(result.violated_theorems)

    def test_pct5b_clean_code_passes(self) -> None:
        lib = TheoremLibrary()
        activated = {"T05": lib.get("T05")}
        result = dual_verify("def f(): _l = 1; return _l", activated,
                             test_passed=True)
        assert result.all_passed
        assert len(result.violated_theorems) == 0


# ═══════════════════════════════════════════════════════════════════
# P-CD5: Activate Function
# ═══════════════════════════════════════════════════════════════════

class TestCD5ActivateFunction:

    def test_pcd5a_keyword_activates_theorem(self) -> None:
        activated = TheoremLibrary().activate({"cache"}, set())
        assert "T01" in activated
        assert "T05" in activated

    def test_pcd5b_element_activates_theorem(self) -> None:
        activated = TheoremLibrary().activate(
            set(), {CodingElement.ERROR_HANDLING})
        assert "T06" in activated

    def test_pcd5c_unknown_keyword_gets_baseline(self) -> None:
        """Unknown keywords → baseline theorems injected."""
        activated = TheoremLibrary().activate({"xyzzy_unknown"}, set())
        assert set(activated.keys()) == BASELINE_THEOREMS

    def test_pcd5d_multiple_triggers(self) -> None:
        activated = TheoremLibrary().activate(
            {"exception", "file"}, {CodingElement.COMPOSITION})
        assert "T06" in activated
        assert "T08" in activated
        assert "T02" in activated

    def test_pcd5e_all_theorems_reachable(self) -> None:
        lib = TheoremLibrary()
        all_kws = set()
        for t in lib.theorems.values():
            all_kws.update(t.triggers)
        activated = lib.activate(all_kws, set(CodingElement))
        assert activated.keys() == lib.all_ids()

    def test_pcd5f_case_insensitive(self) -> None:
        """CD5 normalize: 'Cache' matches triggers containing 'cache'."""
        activated = TheoremLibrary().activate({"Cache"}, set())
        assert "T05" in activated

    def test_pcd5g_dataflow_activates_t01(self) -> None:
        activated = TheoremLibrary().activate(
            set(), {CodingElement.DATA_FLOW})
        assert "T01" in activated

    def test_pcd5h_statemgmt_activates_t05_t07(self) -> None:
        activated = TheoremLibrary().activate(
            set(), {CodingElement.STATE_MANAGEMENT})
        assert "T05" in activated
        assert "T07" in activated


# ═══════════════════════════════════════════════════════════════════
# P-CD7: Process Task end-to-end
# ═══════════════════════════════════════════════════════════════════

class TestCD7ProcessTask:

    def _setup(self):
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary()
        xlib.add(CodingExperience(
            id="E_cache", title="Cache pattern",
            domain=["Python", "caching"],
            theorem_basis={"T05", "T06"},
            context="caching with exception safety",
            pattern="def with_cache(fn): pass",
        ), skip_validation=True)
        return tlib, xlib

    def test_pcd7a_experience_guided(self) -> None:
        tlib, xlib = self._setup()
        ctx = process_task(["cache", "exception"], tlib, xlib,
                           strict_experience=False)
        assert ctx.mode == "experience_guided"
        assert ctx.selected_experience.id == "E_cache"

    def test_pcd7b_theorem_only_on_mismatch(self) -> None:
        tlib, xlib = self._setup()
        ctx = process_task(["database", "connection"], tlib, xlib)
        assert ctx.mode == "theorem_only"

    def test_pcd7c_elements_populated(self) -> None:
        tlib, xlib = self._setup()
        ctx = process_task(["cache", "loop", "type"], tlib, xlib)
        assert CodingElement.STATE_MANAGEMENT in ctx.activated_elements
        assert CodingElement.CONTROL_FLOW in ctx.activated_elements
        assert CodingElement.TYPE_SCHEMA in ctx.activated_elements

    def test_pcd7d_theorems_populated(self) -> None:
        tlib, xlib = self._setup()
        ctx = process_task(["cache", "exception"], tlib, xlib)
        assert "T05" in ctx.activated_theorems
        assert "T06" in ctx.activated_theorems

    def test_pcd7e_strict_coverage_rejects_partial(self) -> None:
        """strict_experience=True: experience must cover all activated theorems."""
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary()
        xlib.add(CodingExperience(
            id="E_partial", title="Partial",
            domain=["Python", "caching"],
            theorem_basis={"T05"},
            context="caching", pattern="pass",
        ), skip_validation=True)
        ctx = process_task(["cache", "exception"], tlib, xlib,
                           strict_experience=True)
        assert ctx.mode == "theorem_only"


# ═══════════════════════════════════════════════════════════════════
# P-H6: Specification Parsing Determinism (conditional)
# ═══════════════════════════════════════════════════════════════════

class TestH6SpecParsingDeterminism:

    def test_ph6a_same_input_same_output(self) -> None:
        kws = ["cache", "exception", "type"]
        assert decompose_task(kws) == decompose_task(kws)

    def test_ph6b_order_independent(self) -> None:
        assert decompose_task(["cache", "loop"]) == decompose_task(["loop", "cache"])

    def test_ph6c_activation_deterministic(self) -> None:
        lib = TheoremLibrary()
        a1 = lib.activate({"cache", "file"}, set())
        a2 = lib.activate({"cache", "file"}, set())
        assert a1.keys() == a2.keys()


# ═══════════════════════════════════════════════════════════════════
# P-H8: Composition Closure (conditional — T_local scope)
# ═══════════════════════════════════════════════════════════════════

class TestH8CompositionClosure:

    def _verify(self, code: str, tids: list[str]) -> list[TheoremCheckResult]:
        lib = TheoremLibrary()
        return verify_theorems(code, {t: lib.get(t) for t in tids})

    def test_ph8a_concat_preserves_t05(self) -> None:
        code = "def a(): _a = 1; return _a\ndef b(): _b = 2; return _b"
        assert all(r.passed for r in self._verify(code, ["T05"]))

    def test_ph8b_nesting_preserves_t06(self) -> None:
        code = ("def outer():\n    try:\n        def inner():\n"
                "            try:\n                risky()\n"
                "            except ValueError:\n                pass\n"
                "        inner()\n    except Exception:\n        pass")
        assert all(r.passed for r in self._verify(code, ["T06"]))

    def test_ph8c_multiple_with_preserves_t08(self) -> None:
        code = ("with open('a') as f1:\n    d = f1.read()\n"
                "with open('b') as f2:\n    d = f2.read()")
        assert all(r.passed for r in self._verify(code, ["T08"]))


# ═══════════════════════════════════════════════════════════════════
# P-H11: Test Environment Reliability (conditional)
# ═══════════════════════════════════════════════════════════════════

class TestH11TestEnvironment:

    def test_ph11a_deterministic_eval(self) -> None:
        assert eval("2 + 3") == eval("2 + 3") == 5

    def test_ph11b_assertion_catches_failure(self) -> None:
        with pytest.raises(AssertionError):
            assert 1 == 2

    def test_ph11c_exception_reliable(self) -> None:
        with pytest.raises(ZeroDivisionError):
            _ = 1 / 0


# ═══════════════════════════════════════════════════════════════════
# P-H13: Verifier Determinism
# ═══════════════════════════════════════════════════════════════════

class TestH13VerifierDeterminism:

    def test_ph13a_same_code_same_result(self) -> None:
        lib = TheoremLibrary()
        code = "global x\nx = 1"
        r1 = lib.get("T05").check(code)
        r2 = lib.get("T05").check(code)
        assert r1.passed == r2.passed
        assert r1.detail == r2.detail

    def test_ph13b_all_checkers_deterministic(self) -> None:
        lib = TheoremLibrary()
        code = "def f(x): return x + 1"
        for t in lib.theorems.values():
            r1 = t.check(code)
            r2 = t.check(code)
            assert r1.passed == r2.passed


# ═══════════════════════════════════════════════════════════════════
# Experience Library Operations
# ═══════════════════════════════════════════════════════════════════

class TestExperienceLibrary:

    def _make_lib(self) -> ExperienceLibrary:
        xlib = ExperienceLibrary()
        xlib.add(CodingExperience(
            id="E01", title="Cache", domain=["Python"],
            theorem_basis={"T05", "T06"}, context="caching", pattern="pass",
        ), skip_validation=True)
        xlib.add(CodingExperience(
            id="E02", title="File IO", domain=["Python"],
            theorem_basis={"T08", "T10"}, context="file reading",
            pattern="pass",
        ), skip_validation=True)
        return xlib

    def test_add_and_count(self) -> None:
        assert self._make_lib().count == 2

    def test_remove(self) -> None:
        xlib = self._make_lib()
        assert xlib.remove("E01") is not None
        assert xlib.count == 1

    def test_search_by_keyword(self) -> None:
        results = self._make_lib().search({"caching"}, set())
        assert len(results) == 1 and results[0].id == "E01"

    def test_search_excludes_expired(self) -> None:
        xlib = ExperienceLibrary()
        xlib.add(CodingExperience(
            id="E_old", title="Old", domain=["Python"],
            theorem_basis={"T05"}, context="caching", pattern="pass",
            validity_start=100, validity_end=200,
        ), skip_validation=True)
        assert len(xlib.search({"caching"}, set(), now=300)) == 0

    def test_search_sorts_by_coverage(self) -> None:
        xlib = ExperienceLibrary()
        xlib.add(CodingExperience(
            id="E_narrow", title="Narrow", domain=["Python"],
            theorem_basis={"T05"}, context="caching", pattern="pass",
        ), skip_validation=True)
        xlib.add(CodingExperience(
            id="E_broad", title="Broad", domain=["Python"],
            theorem_basis={"T05", "T06", "T08"}, context="caching",
            pattern="pass",
        ), skip_validation=True)
        results = xlib.search({"caching"}, {"T05"})
        assert results[0].id == "E_broad"

    def test_search_empty_keywords(self) -> None:
        assert len(self._make_lib().search(set(), set())) == 0

    def test_search_strict_rejects_partial(self) -> None:
        xlib = ExperienceLibrary()
        xlib.add(CodingExperience(
            id="E1", title="Partial", domain=["Python"],
            theorem_basis={"T05"}, context="caching", pattern="pass",
        ), skip_validation=True)
        results = xlib.search({"caching"}, {"T05", "T06"},
                              strict_coverage=True)
        assert len(results) == 0
