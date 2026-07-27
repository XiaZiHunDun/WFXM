"""CD0/CD7: Coding Knowledge Context and Task Processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from butler.dev_engine.coding_knowledge.elements import CodingElement, decompose_task
from butler.dev_engine.coding_knowledge.experience import CodingExperience, ExperienceLibrary
from butler.dev_engine.coding_knowledge.theorems import CodingTheorem, TheoremLibrary


@dataclass
class CodingKnowledgeContext:
    """Full context for a coding task after knowledge layer processing."""

    task_keywords: Set[str]
    activated_elements: Set[CodingElement]
    activated_theorems: Dict[str, CodingTheorem]
    selected_experience: Optional[CodingExperience]
    mode: str  # "experience_guided" or "theorem_only"


def process_task(keywords: List[str],
                 theorem_lib: TheoremLibrary,
                 experience_lib: ExperienceLibrary,
                 now: Optional[float] = None,
                 strict_experience: bool = True,
                 *,
                 project_id: str = "",
                 stack_tags: frozenset[str] | set[str] | None = None,
                 inferred_task_id: str = "") -> CodingKnowledgeContext:
    """End-to-end coding knowledge processing (CD7).

    PLAN phase: decompose → activate theorems → search experience.
    """
    kw_set = set(keywords)
    elements = decompose_task(keywords)
    activated = theorem_lib.activate(kw_set, elements)
    activated_ids = set(activated.keys())

    candidates = experience_lib.search(
        kw_set, activated_ids, now,
        strict_coverage=strict_experience,
        project_id=project_id,
        stack_tags=stack_tags,
        inferred_task_id=inferred_task_id,
    )
    selected = candidates[0] if candidates else None
    mode = "experience_guided" if selected else "theorem_only"

    return CodingKnowledgeContext(
        task_keywords=kw_set,
        activated_elements=elements,
        activated_theorems=activated,
        selected_experience=selected,
        mode=mode,
    )


__all__ = [
    "CodingKnowledgeContext",
    "process_task",
]