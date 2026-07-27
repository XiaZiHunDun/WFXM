"""Butler v4 L4 Coding Knowledge Layer — 定理库 + 经验库 + 双重验证门.

This module re-exports from the new ``butler.dev_engine.coding_knowledge`` package
for backward compatibility.

.. deprecated:: 4.5
    Import from ``butler.dev_engine.coding_knowledge`` package instead. This module will
    be removed in a future version.

Theory: docs/architecture/v4-dev-engine-theory.md Chapter 9 (v1.4)
Axioms: CA1-CA4 | Definitions: CD0-CD8 | Theorems: CT1-CT5
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.dev_engine.coding_knowledge is deprecated. "
    "Import from butler.dev_engine.coding_knowledge package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from butler.dev_engine.coding_knowledge.elements import (
    BASELINE_THEOREMS,
    CodingElement,
    ELEMENT_THEOREM_MAP,
    ELEMENT_VERIFICATION_PROPERTIES,
    decompose_task,
    _normalize_keywords,
)
from butler.dev_engine.coding_knowledge.theorems import (
    CodingTheorem,
    TheoremCheckResult,
    TheoremChecker,
    TheoremLibrary,
    THEOREM_CHECKERS,
    build_default_theorem_library,
)
from butler.dev_engine.coding_knowledge.verification import (
    DualVerificationResult,
    dual_verify,
    verify_theorems,
)
from butler.dev_engine.coding_knowledge.context import (
    CodingKnowledgeContext,
    process_task,
)
from butler.dev_engine.coding_knowledge.experience import (
    CodingExperience,
    ExperienceLibrary,
)
from butler.dev_engine.coding_knowledge.generation import (
    GenTCResult,
    SynthConstraint,
    SynthResult,
    TestCase,
    extract_experience_candidate,
    format_coding_guidance_block,
    generate_test_cases,
    synthesize,
)

__all__ = [
    "BASELINE_THEOREMS",
    "CodingElement",
    "ELEMENT_THEOREM_MAP",
    "ELEMENT_VERIFICATION_PROPERTIES",
    "decompose_task",
    "_normalize_keywords",
    "CodingTheorem",
    "TheoremCheckResult",
    "TheoremChecker",
    "TheoremLibrary",
    "THEOREM_CHECKERS",
    "build_default_theorem_library",
    "DualVerificationResult",
    "dual_verify",
    "verify_theorems",
    "CodingKnowledgeContext",
    "process_task",
    "CodingExperience",
    "ExperienceLibrary",
    "GenTCResult",
    "SynthConstraint",
    "SynthResult",
    "TestCase",
    "extract_experience_candidate",
    "format_coding_guidance_block",
    "generate_test_cases",
    "synthesize",
]