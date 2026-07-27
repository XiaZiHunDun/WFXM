"""Coding Elements — Seven fundamental coding elements (CA1).

CD1: Element taxonomy and decomposition.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Set


class CodingElement(str, Enum):
    """Seven fundamental coding elements (CA1)."""

    DATA_FLOW = "DataFlow"
    CONTROL_FLOW = "ControlFlow"
    STATE_MANAGEMENT = "StateManagement"
    COMPOSITION = "Composition"
    BOUNDARY_INTERFACE = "BoundaryInterface"
    ERROR_HANDLING = "ErrorHandling"
    TYPE_SCHEMA = "TypeSchema"


ELEMENT_VERIFICATION_PROPERTIES: Dict[CodingElement, List[str]] = {
    CodingElement.DATA_FLOW: [
        "no_state_mutation",
        "input_immutable",
        "pipeline_direction_consistent",
    ],
    CodingElement.CONTROL_FLOW: [
        "termination_guaranteed",
        "branch_completeness",
        "no_dead_code",
    ],
    CodingElement.STATE_MANAGEMENT: [
        "scope_minimized",
        "change_predictable",
        "no_accidental_sharing",
    ],
    CodingElement.COMPOSITION: [
        "type_compatible",
        "effect_order_correct",
        "no_cyclic_dependency",
    ],
    CodingElement.BOUNDARY_INTERFACE: [
        "contract_coverage",
        "resource_release",
        "input_validation",
    ],
    CodingElement.ERROR_HANDLING: [
        "exception_coverage",
        "error_not_lost",
        "recovery_consistency",
    ],
    CodingElement.TYPE_SCHEMA: [
        "type_closed",
        "pattern_match_complete",
        "constraint_satisfied",
    ],
}

ELEMENT_THEOREM_MAP: Dict[CodingElement, Set[str]] = {
    CodingElement.DATA_FLOW: {"T01"},
    CodingElement.CONTROL_FLOW: {"T04"},
    CodingElement.STATE_MANAGEMENT: {"T05", "T07"},
    CodingElement.COMPOSITION: {"T02"},
    CodingElement.BOUNDARY_INTERFACE: {"T08", "T09", "T10"},
    CodingElement.ERROR_HANDLING: {"T06"},
    CodingElement.TYPE_SCHEMA: {"T03"},
}

BASELINE_THEOREMS = {"T03", "T10"}

_KEYWORD_ELEMENT_MAP: Dict[str, Set[CodingElement]] = {
    "filter": {CodingElement.DATA_FLOW, CodingElement.CONTROL_FLOW},
    "map": {CodingElement.DATA_FLOW},
    "reduce": {CodingElement.DATA_FLOW},
    "transform": {CodingElement.DATA_FLOW},
    "pipeline": {CodingElement.DATA_FLOW, CodingElement.COMPOSITION},
    "pure": {CodingElement.DATA_FLOW},
    "if": {CodingElement.CONTROL_FLOW},
    "loop": {CodingElement.CONTROL_FLOW},
    "while": {CodingElement.CONTROL_FLOW},
    "for": {CodingElement.CONTROL_FLOW},
    "recursive": {CodingElement.CONTROL_FLOW},
    "cache": {CodingElement.STATE_MANAGEMENT},
    "store": {CodingElement.STATE_MANAGEMENT},
    "counter": {CodingElement.STATE_MANAGEMENT},
    "accumulate": {CodingElement.STATE_MANAGEMENT, CodingElement.DATA_FLOW},
    "compose": {CodingElement.COMPOSITION},
    "chain": {CodingElement.COMPOSITION},
    "decorator": {CodingElement.COMPOSITION},
    "api": {CodingElement.BOUNDARY_INTERFACE},
    "fetch": {CodingElement.BOUNDARY_INTERFACE},
    "file": {CodingElement.BOUNDARY_INTERFACE},
    "database": {CodingElement.BOUNDARY_INTERFACE},
    "network": {CodingElement.BOUNDARY_INTERFACE},
    "try": {CodingElement.ERROR_HANDLING},
    "catch": {CodingElement.ERROR_HANDLING},
    "exception": {CodingElement.ERROR_HANDLING},
    "error": {CodingElement.ERROR_HANDLING},
    "fallback": {CodingElement.ERROR_HANDLING},
    "type": {CodingElement.TYPE_SCHEMA},
    "schema": {CodingElement.TYPE_SCHEMA},
    "validate": {CodingElement.TYPE_SCHEMA},
    "struct": {CodingElement.TYPE_SCHEMA},
    "interface": {CodingElement.TYPE_SCHEMA, CodingElement.BOUNDARY_INTERFACE},
}


def decompose_task(keywords: List[str]) -> Set[CodingElement]:
    """Decompose a coding task into activated elements based on keywords."""
    elements: Set[CodingElement] = set()
    for kw in keywords:
        kw_lower = kw.lower()
        for trigger, elems in _KEYWORD_ELEMENT_MAP.items():
            if trigger in kw_lower:
                elements.update(elems)
    return elements


def _normalize_keywords(keywords: Set[str]) -> Set[str]:
    """Normalize keywords to lowercase for consistent matching."""
    return {kw.lower() for kw in keywords}


__all__ = [
    "CodingElement",
    "ELEMENT_VERIFICATION_PROPERTIES",
    "ELEMENT_THEOREM_MAP",
    "BASELINE_THEOREMS",
    "decompose_task",
    "_normalize_keywords",
]