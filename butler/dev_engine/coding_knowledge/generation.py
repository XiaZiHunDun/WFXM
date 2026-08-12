"""CD8: Code Synthesizer and Test Case Generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from butler.dev_engine.coding_knowledge.context import CodingKnowledgeContext
from butler.dev_engine.coding_knowledge.elements import CodingElement
from butler.dev_engine.coding_knowledge.experience import CodingExperience
from butler.dev_engine.coding_knowledge.theorems import CodingTheorem
from butler.dev_engine.coding_knowledge.verification import verify_theorems


@dataclass
class SynthConstraint:
    """A single constraint derived from an activated theorem or experience."""

    source: str
    category: str  # "must", "must_not", "prefer"
    description: str


@dataclass
class SynthResult:
    """Result of CD8 synthesis — constraints + optional template."""

    constraints: List[SynthConstraint]
    template_hint: str = ""
    experience_pattern: str = ""
    activated_theorem_ids: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        must = [c for c in self.constraints if c.category == "must"]
        must_not = [c for c in self.constraints if c.category == "must_not"]
        parts = []
        if must:
            parts.append("MUST: " + "; ".join(c.description for c in must))
        if must_not:
            parts.append("MUST NOT: " + "; ".join(c.description for c in must_not))
        return " | ".join(parts) if parts else "no constraints"


_THEOREM_CONSTRAINTS: Dict[str, List[SynthConstraint]] = {
    "T01": [
        SynthConstraint("T01", "must_not", "avoid nondeterministic calls (random/time/uuid) in pure functions"),
        SynthConstraint("T01", "must", "same input always produces same output"),
    ],
    "T02": [
        SynthConstraint("T02", "must", "functions must return consistent types across all branches"),
        SynthConstraint("T02", "must_not", "avoid returning incompatible types (e.g. str on one branch, int on another)"),
        SynthConstraint("T02", "prefer", "use type annotations on function signatures for composition clarity"),
    ],
    "T03": [
        SynthConstraint("T03", "must_not", "avoid eval()/exec()"),
        SynthConstraint("T03", "must", "use proper type conversions"),
    ],
    "T04": [
        SynthConstraint("T04", "must", "every loop/recursion must have a termination condition"),
        SynthConstraint("T04", "must_not", "avoid while True without break/return"),
    ],
    "T05": [
        SynthConstraint("T05", "must_not", "avoid global mutable state"),
        SynthConstraint("T05", "must", "minimize mutable state scope"),
    ],
    "T06": [
        SynthConstraint("T06", "must", "every try must have proper exception handling"),
        SynthConstraint("T06", "must_not", "avoid bare except:pass"),
    ],
    "T07": [
        SynthConstraint("T07", "must", "operations must be idempotent — calling twice yields the same result as calling once"),
        SynthConstraint("T07", "must_not", "avoid list.append/extend in functions that may be retried"),
        SynthConstraint("T07", "must_not", "avoid file open in append mode for idempotent operations"),
        SynthConstraint("T07", "prefer", "use dict assignment or set operations instead of list append for idempotent writes"),
    ],
    "T08": [
        SynthConstraint("T08", "must", "use context managers (with) for resources"),
        SynthConstraint("T08", "must_not", "avoid open() without with/close/finally"),
    ],
    "T09": [
        SynthConstraint("T09", "must", "check HTTP response status after requests"),
    ],
    "T10": [
        SynthConstraint("T10", "must", "validate all external input before use"),
        SynthConstraint("T10", "must_not", "never trust user/network input directly"),
    ],
}


def synthesize(ctx: CodingKnowledgeContext) -> SynthResult:
    """CD8 Synthesizer: derive constraints and template from knowledge context."""
    constraints: List[SynthConstraint] = []
    for tid in sorted(ctx.activated_theorems.keys()):
        cs = _THEOREM_CONSTRAINTS.get(tid, [])
        constraints.extend(cs)

    template_hint = ""
    experience_pattern = ""
    if ctx.selected_experience:
        experience_pattern = ctx.selected_experience.pattern
        constraints.append(SynthConstraint(
            f"EXP:{ctx.selected_experience.id}",
            "prefer",
            f"follow pattern from experience '{ctx.selected_experience.title}'",
        ))

    if CodingElement.ERROR_HANDLING in ctx.activated_elements:
        template_hint += "try:\n    ...\nexcept SpecificError as e:\n    handle(e)\n"
    if CodingElement.BOUNDARY_INTERFACE in ctx.activated_elements:
        template_hint += "with resource_manager() as r:\n    ...\n"

    return SynthResult(
        constraints=constraints,
        template_hint=template_hint,
        experience_pattern=experience_pattern,
        activated_theorem_ids=sorted(ctx.activated_theorems.keys()),
    )


@dataclass
class TestCase:
    """A generated test case from equivalence class partitioning (H10)."""

    id: str
    category: str  # "normal", "boundary", "error", "negative"
    description: str
    input_sketch: str
    expected_behavior: str
    theorem_source: str = ""


@dataclass
class GenTCResult:
    """Result of test case generation."""

    test_cases: List[TestCase]
    coverage_classes: List[str]

    @property
    def count(self) -> int:
        return len(self.test_cases)

    @property
    def category_breakdown(self) -> Dict[str, int]:
        breakdown: Dict[str, int] = {}
        for tc in self.test_cases:
            breakdown[tc.category] = breakdown.get(tc.category, 0) + 1
        return breakdown


THEOREM_TEST_PATTERNS: Dict[str, List[TestCase]] = {
    "T01": [
        TestCase("T01_norm", "normal", "same input → same output", "f(x)", "f(x) == f(x)", "T01"),
        TestCase("T01_bound", "boundary", "empty/null input determinism", "f(None), f([])", "consistent result", "T01"),
    ],
    "T02": [
        TestCase("T02_norm", "normal", "composed functions type-compatible", "g(f(x))", "no TypeError", "T02"),
        TestCase("T02_neg", "negative", "incompatible return types detected", "f() returns int or str", "checker flags violation", "T02"),
        TestCase("T02_bound", "boundary", "None return in optional chain", "f() → None | T, g(T)", "handles None gracefully", "T02"),
    ],
    "T03": [
        TestCase("T03_norm", "normal", "valid typed input accepted", "valid_typed_value", "no TypeError", "T03"),
        TestCase("T03_neg", "negative", "invalid type rejected", "wrong_type_value", "raises TypeError/ValueError", "T03"),
    ],
    "T04": [
        TestCase("T04_norm", "normal", "finite input terminates", "small_collection", "returns in finite time", "T04"),
        TestCase("T04_bound", "boundary", "empty input terminates", "empty_input", "returns immediately", "T04"),
        TestCase("T04_bound2", "boundary", "large input terminates", "max_size_input", "returns within timeout", "T04"),
    ],
    "T05": [
        TestCase("T05_norm", "normal", "no external state mutation", "call_function()", "global state unchanged", "T05"),
    ],
    "T06": [
        TestCase("T06_norm", "normal", "normal execution succeeds", "valid_input", "success", "T06"),
        TestCase("T06_err", "error", "error leaves no side effects", "error_trigger", "state unchanged after error", "T06"),
        TestCase("T06_bound", "boundary", "exception propagation correct", "edge_case", "proper exception type", "T06"),
    ],
    "T07": [
        TestCase("T07_norm", "normal", "calling twice yields same result as once", "op(); op()", "state == after single op()", "T07"),
        TestCase("T07_neg", "negative", "append in retry context detected", "retry(lambda: items.append(x))", "checker flags non-idempotent", "T07"),
        TestCase("T07_bound", "boundary", "set/dict operations are idempotent", "d[k]=v; d[k]=v", "state unchanged after repeat", "T07"),
    ],
    "T08": [
        TestCase("T08_norm", "normal", "resource acquired and released", "normal_op", "resource closed", "T08"),
        TestCase("T08_err", "error", "resource released on error", "error_during_use", "resource still closed", "T08"),
    ],
    "T09": [
        TestCase("T09_norm", "normal", "API success path", "valid_request", "proper response handling", "T09"),
        TestCase("T09_err", "error", "API error response handled", "error_response", "graceful degradation", "T09"),
        TestCase("T09_bound", "boundary", "API timeout handled", "slow_endpoint", "timeout exception caught", "T09"),
    ],
    "T10": [
        TestCase("T10_norm", "normal", "valid input accepted", "clean_input", "processed correctly", "T10"),
        TestCase("T10_neg", "negative", "malicious input rejected", "injection_attempt", "sanitized/rejected", "T10"),
        TestCase("T10_bound", "boundary", "empty input handled", "empty_string", "no crash", "T10"),
    ],
}


def generate_test_cases(ctx: CodingKnowledgeContext) -> GenTCResult:
    """CD6 GenTC: Generate test cases via equivalence class partitioning (H10)."""
    test_cases: List[TestCase] = []
    coverage_classes: List[str] = []

    for tid in sorted(ctx.activated_theorems.keys()):
        patterns = THEOREM_TEST_PATTERNS.get(tid, [])
        for p in patterns:
            tc = TestCase(
                id=f"{p.id}_{len(test_cases)}",
                category=p.category,
                description=p.description,
                input_sketch=p.input_sketch,
                expected_behavior=p.expected_behavior,
                theorem_source=tid,
            )
            test_cases.append(tc)
        if patterns:
            coverage_classes.append(f"{tid}: {len(patterns)} equivalence classes")

    for elem in sorted(ctx.activated_elements, key=lambda e: e.value):
        tc = TestCase(
            id=f"ELEM_{elem.value}_{len(test_cases)}",
            category="normal",
            description=f"element {elem.value} basic behavior",
            input_sketch="standard_input",
            expected_behavior=f"{elem.value} properties hold",
        )
        test_cases.append(tc)
        coverage_classes.append(f"Element:{elem.value}")

    return GenTCResult(test_cases=test_cases, coverage_classes=coverage_classes)


def format_coding_guidance_block(ctx: CodingKnowledgeContext, *, max_cases: int = 6) -> str:
    """Format Synth + GenTC output for delegate/dev prompt injection (O5)."""
    synth = synthesize(ctx)
    gentc = generate_test_cases(ctx)
    lines = ["<coding-guidance>"]
    if synth.constraints:
        lines.append("## Theorem constraints")
        for c in synth.constraints[:12]:
            lines.append(f"- [{c.source}] ({c.category}) {c.description}")
    if synth.template_hint.strip():
        lines.append("## Suggested template")
        lines.append(synth.template_hint.strip())
    if synth.experience_pattern:
        lines.append(f"## Experience pattern\n{synth.experience_pattern[:400]}")
    if gentc.test_cases:
        lines.append("## Equivalence-class test sketches")
        for tc in gentc.test_cases[:max_cases]:
            lines.append(
                f"- ({tc.category}) {tc.description}: {tc.input_sketch} → {tc.expected_behavior}"
            )
    lines.append("</coding-guidance>")
    return "\n".join(lines)


def extract_experience_candidate(
    task_description: str,
    code_snippets: List[str],
    activated_theorems: Dict[str, CodingTheorem],
    *,
    domain: Optional[List[str]] = None,
) -> Optional["CodingExperience"]:
    """Extract a candidate experience from a successfully completed task."""
    from butler.dev_engine.coding_knowledge.experience import CodingExperience

    if not code_snippets or not activated_theorems:
        return None

    best_snippet = max(code_snippets, key=len)
    if len(best_snippet) < 20:
        return None

    thm_results = verify_theorems(best_snippet, activated_theorems)
    failed = [r for r in thm_results if not r.passed]
    if failed:
        return None

    import uuid
    experience_id = f"EXP_{uuid.uuid4().hex[:8]}"

    return CodingExperience(
        id=experience_id,
        title=task_description[:50],
        domain=domain or ["general"],
        theorem_basis=set(activated_theorems.keys()),
        context=task_description[:200],
        pattern=best_snippet,
        benchmarks={},
    )


__all__ = [
    "SynthConstraint",
    "SynthResult",
    "synthesize",
    "TestCase",
    "GenTCResult",
    "generate_test_cases",
    "format_coding_guidance_block",
    "extract_experience_candidate",
]
