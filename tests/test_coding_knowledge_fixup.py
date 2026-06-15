"""Tests for coding knowledge FIX-phase reactivation (P1)."""

from __future__ import annotations

import json

from butler.dev_engine.coding_knowledge import (
    CodingExperience,
    ExperienceLibrary,
    TheoremLibrary,
)
from butler.dev_engine.coding_knowledge_fixup import (
    keywords_from_verify_fail,
    reactivate_coding_knowledge_on_verify_fail,
)
from butler.dev_engine.dev_state import (
    CodingKnowledgeSummary,
    DevState,
    Diagnostic,
    DiagSeverity,
    VerifyResult,
    VerifyStatus,
)
from butler.dev_engine.fix_strategy import FixLevel, enrich_fix_hint
from butler.memory.memory_scope import MemoryScope


def test_keywords_from_verify_fail_extracts_pytest_tokens():
    vr = VerifyResult(
        status=VerifyStatus.FAIL,
        diagnostics=[
            Diagnostic(
                file="test_x.py",
                line=10,
                severity=DiagSeverity.ERROR,
                message="AssertionError: assert greet() == 'hello'",
                source="pytest",
            )
        ],
        output_tail="FAILED test_x.py::test_greet - AssertionError",
    )
    kws = keywords_from_verify_fail(vr)
    assert "pytest" in kws
    assert "assertionerror" in kws or "assert" in kws


def test_reactivate_updates_experience_on_verify_fail(tmp_path, monkeypatch):
    butler_home = tmp_path / "butler_home"
    butler_home.mkdir(parents=True, exist_ok=True)
    tenant = butler_home / "coding_experiences.json"
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary(theorem_lib=tlib)
    from butler.dev_engine.b9_experience_retrieval import B9_EXPERIENCE_THEOREM_BASIS

    exp = CodingExperience(
        id="B9_EX_verify_fix",
        title="Fix greet verify",
        domain=["pytest", "verify"],
        theorem_basis=set(B9_EXPERIENCE_THEOREM_BASIS),
        context="greet verify fail",
        pattern="read test then patch greet return hello",
        benchmarks={"retrieval_keywords": ["pytest", "verify", "greet", "hello"]},
        scope=MemoryScope(level="tenant", visibility="global", source="b9"),
    )
    xlib.add(exp, skip_validation=True)
    xlib.save_to_file(str(tenant))

    monkeypatch.setattr("butler.config.get_butler_home", lambda: butler_home)
    monkeypatch.setattr(
        "butler.memory.memory_scope.tenant_coding_experiences_path",
        lambda _home: tenant,
    )
    monkeypatch.setattr(
        "butler.ops.eval_config_overrides.effective_coding_knowledge_strict",
        lambda _default: False,
    )

    state = DevState(task_description="Fix greet.py return hello")
    state.coding_knowledge = CodingKnowledgeSummary(mode="theorem_only")
    state._delegate_keywords = ["fix", "greet"]
    state._delegate_project_id = ""
    state._delegate_stack_tags = frozenset()
    state._inferred_task_id = ""
    state._delegate_project = None
    state.verify_result = VerifyResult(
        status=VerifyStatus.FAIL,
        diagnostics=[
            Diagnostic(
                file="test_b9.py",
                line=3,
                severity=DiagSeverity.ERROR,
                message="AssertionError expected hello got hi",
                source="pytest",
            )
        ],
        output_tail="FAILED test_b9.py::test_greet",
    )

    out = reactivate_coding_knowledge_on_verify_fail(state)
    assert out["reactivated"] is True
    assert state.coding_knowledge.experience_id == "B9_EX_verify_fix"
    assert state.coding_knowledge.mode == "experience_guided"
    assert getattr(state, "_coding_knowledge_reactivation_count", 0) == 1
    ctx = getattr(state, "_coding_knowledge_ctx", None)
    assert ctx is not None
    assert ctx.selected_experience is not None


def test_enrich_fix_hint_appends_pattern():
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary(theorem_lib=tlib)
    exp = CodingExperience(
        id="B9_EX_hint",
        title="hint",
        domain=["pytest"],
        theorem_basis={"T01"},
        context="ctx",
        pattern="patch greet return hello not hi",
        benchmarks={"retrieval_keywords": ["greet"]},
        scope=MemoryScope(level="tenant", visibility="global", source="b9"),
    )
    xlib.add(exp, skip_validation=True)
    from butler.dev_engine.coding_knowledge import process_task

    ctx = process_task(["greet", "pytest"], tlib, xlib, strict_experience=False)
    ctx.selected_experience = exp
    state = DevState()
    state._coding_knowledge_ctx = ctx
    hint = enrich_fix_hint(FixLevel.STRUCTURAL, state)
    assert hint.startswith("structural:")
    assert "patch greet return hello" in hint
