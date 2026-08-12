"""CD6: Dual Verification Gate (CA4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from butler.dev_engine.coding_knowledge.theorems import CodingTheorem, TheoremCheckResult


@dataclass
class DualVerificationResult:
    """Combined result of theorem + test verification (CD6)."""

    theorem_results: List[TheoremCheckResult] = field(default_factory=list)
    test_passed: bool = False
    test_detail: str = ""
    failed_test_cases: List[str] = field(default_factory=list)

    @property
    def theorem_passed(self) -> bool:
        if not self.theorem_results:
            return False
        return all(r.passed for r in self.theorem_results)

    @property
    def all_passed(self) -> bool:
        return self.theorem_passed and self.test_passed

    @property
    def violated_theorems(self) -> List[str]:
        return [r.theorem_id for r in self.theorem_results if not r.passed]


def verify_theorems(code: str,
                    activated: Dict[str, CodingTheorem]) -> List[TheoremCheckResult]:
    """Verify_thm: check code against all activated theorems (CD6)."""
    return [t.check(code) for t in activated.values()]


def dual_verify(code: str, activated_theorems: Dict[str, CodingTheorem],
                test_passed: bool, test_detail: str = "",
                failed_test_cases: Optional[List[str]] = None,
                ) -> DualVerificationResult:
    """Full dual verification gate (CA4, CD6)."""
    thm_results = verify_theorems(code, activated_theorems)
    return DualVerificationResult(
        theorem_results=thm_results,
        test_passed=test_passed,
        test_detail=test_detail,
        failed_test_cases=failed_test_cases or [],
    )


__all__ = [
    "DualVerificationResult",
    "verify_theorems",
    "dual_verify",
]
