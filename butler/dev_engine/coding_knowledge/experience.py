"""CA3: Experience Library (CD4)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, cast

from butler.dev_engine.coding_knowledge.elements import _normalize_keywords
from butler.dev_engine.coding_knowledge.seed_experiences import SEED_EXPERIENCES
from butler.dev_engine.coding_knowledge.theorems import TheoremLibrary
from butler.dev_engine.coding_knowledge.verification import verify_theorems
from butler.dev_engine.coding_knowledge_ops import experience_retrieval_eligible_safe
from butler.dev_engine.coding_knowledge_ops import experience_retrieval_rank_bonus_safe
from butler.dev_engine.coding_knowledge_ops import infer_b9_task_id_safe
from butler.memory.memory_scope import (
    MemoryScope,
    backfill_experience_scope,
    infer_default_scope,
    project_coding_experiences_path,
)

if TYPE_CHECKING:
    from butler.memory.memory_scope import MemoryScope


def _default_memory_scope() -> "MemoryScope":
    return MemoryScope()


@dataclass
class CodingExperience:
    """A coding experience: a time-bound best practice (CA3, CD4)."""

    id: str
    title: str
    domain: List[str]
    theorem_basis: Set[str]  # B_x
    context: str
    pattern: str
    benchmarks: Dict[str, str] = field(default_factory=dict)
    validity_start: float = 0.0
    validity_end: float = float("inf")
    supersedes: Optional[str] = None
    scope: "MemoryScope" = field(default_factory=lambda: _default_memory_scope())

    def is_valid(self, now: Optional[float] = None) -> bool:
        t = now if now is not None else time.time()
        return self.validity_start <= t <= self.validity_end

    def covers_theorems(self, activated: Set[str]) -> bool:
        return activated.issubset(self.theorem_basis)


class ExperienceLibrary:
    """Manages the experience library (CA3a/CA3b, CD4)."""

    def __init__(self, theorem_lib: Optional[TheoremLibrary] = None) -> None:
        self._experiences: Dict[str, CodingExperience] = {}
        self._theorem_lib = theorem_lib

    def _validate_pattern(self, exp: CodingExperience) -> Tuple[bool, str]:
        """Validate experience pattern against theorem basis (P-CT3a)."""
        if not self._theorem_lib or not exp.theorem_basis:
            return True, "no theorem lib or empty basis"
        activated = {}
        for tid in exp.theorem_basis:
            t = self._theorem_lib.get(tid)
            if t:
                activated[tid] = t
        results = verify_theorems(exp.pattern, activated)
        failed = [r for r in results if not r.passed]
        if failed:
            details = "; ".join(f"{r.theorem_id}: {r.detail}" for r in failed)
            return False, f"pattern violates theorems: {details}"
        return True, "ok"

    def add(self, exp: CodingExperience,
            skip_validation: bool = False) -> Tuple[bool, str]:
        """Add experience with optional theorem validation (CT3 safety)."""
        if not skip_validation:
            ok, detail = self._validate_pattern(exp)
            if not ok:
                return False, detail
        self._experiences[exp.id] = exp
        return True, "ok"

    def remove(self, exp_id: str) -> Optional[CodingExperience]:
        return self._experiences.pop(exp_id, None)

    def get(self, exp_id: str) -> Optional[CodingExperience]:
        return self._experiences.get(exp_id)

    @property
    def count(self) -> int:
        return len(self._experiences)

    @staticmethod
    def _is_b9_experience(exp: "CodingExperience") -> bool:
        return any(str(d).lower() == "b9" for d in exp.domain)

    @staticmethod
    def _experience_search_blob(exp: "CodingExperience") -> str:
        parts = [exp.context, exp.title, exp.pattern[:400]]
        parts.extend(str(d) for d in exp.domain)
        parts.extend(str(v) for v in exp.benchmarks.values())
        return " ".join(parts).lower()

    @classmethod
    def _keyword_match_score(cls, exp: "CodingExperience", normalized: Set[str]) -> int:
        blob = cls._experience_search_blob(exp)
        retrieval = str(exp.benchmarks.get("retrieval_keywords", "")).lower()
        score = 0
        for kw in normalized:
            if retrieval and kw in retrieval:
                score += 3
            elif kw in blob:
                score += 1
        return score

    @staticmethod
    def _is_failure_experience(exp: "CodingExperience") -> bool:
        return (
            str(exp.id).startswith("B9_FAIL_")
            or "failure" in [str(d).lower() for d in exp.domain]
        )

    @staticmethod
    def _failure_experience_allowed(
        exp: "CodingExperience",
        *,
        failure_class: str,
    ) -> bool:
        """B9_FAIL_* rows only when classification explicitly matches."""
        if not ExperienceLibrary._is_failure_experience(exp):
            return True
        want = (failure_class or "").strip().lower()
        if not want:
            return False
        have = str(exp.benchmarks.get("failure_class") or "").strip().lower()
        if have:
            return have == want
        for dom in exp.domain:
            d = str(dom).lower()
            if d not in ("b9", "failure", "auto", "prod_shaped", "pytest"):
                return d == want
        return False

    def search(self, keywords: Set[str], activated_theorems: Set[str],
               now: Optional[float] = None,
               strict_coverage: bool = False,
               *,
               project_id: str = "",
               stack_tags: frozenset[str] | set[str] | None = None,
               failure_class: str = "",
               inferred_task_id: str = "") -> List[CodingExperience]:
        """Retrieve valid, compatible experiences sorted by coverage."""
        normalized = _normalize_keywords(keywords)
        task_id = (inferred_task_id or "").strip()
        if not task_id:
            task_id = infer_b9_task_id_safe(" ".join(sorted(keywords)))
        scope_tags = frozenset(stack_tags or ())
        results = []
        for exp in self._experiences.values():
            if not exp.is_valid(now):
                continue
            if not self._failure_experience_allowed(exp, failure_class=failure_class):
                continue
            if not self._retrieval_eligible(
                exp,
                normalized,
                inferred_task_id=task_id,
            ):
                continue
            if project_id or scope_tags:
                if not exp.scope.visible_to(project_id=project_id, stack_tags=scope_tags):
                    continue
            if self._keyword_match_score(exp, normalized) <= 0:
                continue
            if activated_theorems:
                is_b9 = self._is_b9_experience(exp)
                if strict_coverage and not is_b9:
                    if not exp.covers_theorems(activated_theorems):
                        continue
                elif strict_coverage and is_b9:
                    if not bool(exp.theorem_basis & activated_theorems):
                        continue
                elif not bool(exp.theorem_basis & activated_theorems):
                    continue
            results.append(exp)
        results.sort(
            key=lambda e: (
                self._keyword_match_score(e, normalized)
                + self._retrieval_rank_bonus(e, normalized, task_id, project_id),
                1 if self._is_b9_experience(e) else 0,
                len(e.theorem_basis),
            ),
            reverse=True,
        )
        return results

    @classmethod
    def _retrieval_eligible(
        cls,
        exp: "CodingExperience",
        normalized: Set[str],
        *,
        inferred_task_id: str,
    ) -> bool:
        return cast(bool, experience_retrieval_eligible_safe(
            experience_id=exp.id,
            normalized_keywords=normalized,
            inferred_task_id=inferred_task_id,
            benchmarks=exp.benchmarks,
        ))

    @classmethod
    def _retrieval_rank_bonus(
        cls,
        exp: "CodingExperience",
        normalized: Set[str],
        inferred_task_id: str,
        project_id: str,
    ) -> int:
        return cast(int, experience_retrieval_rank_bonus_safe(
            experience_id=exp.id,
            normalized_keywords=normalized,
            inferred_task_id=inferred_task_id,
            project_id=project_id,
            benchmarks=exp.benchmarks,
            scope_level=exp.scope.level,
            scope_project_id=exp.scope.project_id,
            scope_source=exp.scope.source,
            domain=list(exp.domain),
        ))

    @classmethod
    def load_merged_for_project(
        cls,
        *,
        tenant_path: str,
        project_workspace: str | None = None,
        theorem_lib: Optional["TheoremLibrary"] = None,
    ) -> "ExperienceLibrary":
        """Load L4 tenant corpus + optional L3 project file into one library."""
        merged = cls.load_from_file(tenant_path, theorem_lib=theorem_lib)
        if project_workspace:
            proj_path = project_coding_experiences_path(project_workspace)
            proj_lib = cls.load_from_file(str(proj_path), theorem_lib=theorem_lib)
            for exp_id, exp in proj_lib._experiences.items():
                merged._experiences[exp_id] = exp
        return merged

    def backfill_scopes(self) -> int:
        """Infer MemoryScope on legacy rows; return count updated."""
        updated = 0
        for exp in self._experiences.values():
            if backfill_experience_scope(exp):
                updated += 1
        return updated

    def replace(self, old_id: str, new_exp: CodingExperience,
                skip_validation: bool = False) -> Tuple[bool, str]:
        """Replace old experience with new one (CT3 safety)."""
        if old_id not in self._experiences:
            return False, f"old experience {old_id} not found"
        if not skip_validation:
            ok, detail = self._validate_pattern(new_exp)
            if not ok:
                return False, detail
        new_exp.supersedes = old_id
        self._experiences.pop(old_id)
        self._experiences[new_exp.id] = new_exp
        return True, "ok"

    def renew(self, exp_id: str, extend_days: float = 90.0) -> bool:
        """Extend an experience's validity window on successful use."""
        exp = self._experiences.get(exp_id)
        if exp is None:
            return False
        exp.validity_end = max(exp.validity_end, time.time() + extend_days * 86400)
        return True

    def demote(self, exp_id: str, shrink_days: float = 30.0) -> bool:
        """Shrink an experience's validity window on failed evaluation."""
        exp = self._experiences.get(exp_id)
        if exp is None:
            return False
        new_end = exp.validity_end - shrink_days * 86400
        exp.validity_end = max(new_end, time.time())
        return True

    def expire_stale(self, now: Optional[float] = None) -> List[str]:
        """Remove experiences whose validity window has ended. Returns removed IDs."""
        t = now if now is not None else time.time()
        stale = [eid for eid, exp in self._experiences.items()
                 if exp.validity_end < t]
        for eid in stale:
            del self._experiences[eid]
        return stale

    def lifecycle_pass(self, eval_results: Dict[str, bool],
                       now: Optional[float] = None) -> Dict[str, Any]:
        """Run a full lifecycle pass: renew successes, demote failures, expire stale."""
        renewed = 0
        demoted = 0
        for eid, success in eval_results.items():
            if success:
                if self.renew(eid):
                    renewed += 1
            else:
                if self.demote(eid):
                    demoted += 1
        expired = self.expire_stale(now)
        return {
            "renewed": renewed,
            "demoted": demoted,
            "expired": len(expired),
            "expired_ids": expired,
            "total_remaining": self.count,
        }

    def save_to_file(self, path: str) -> None:
        """Persist library to JSON (CA3b — preserves validity windows)."""
        records = []
        for exp in self._experiences.values():
            records.append({
                "id": exp.id,
                "title": exp.title,
                "domain": exp.domain,
                "theorem_basis": sorted(exp.theorem_basis),
                "context": exp.context,
                "pattern": exp.pattern,
                "benchmarks": exp.benchmarks,
                "validity_start": exp.validity_start,
                "validity_end": exp.validity_end,
                "supersedes": exp.supersedes,
                "scope": exp.scope.to_dict(),
            })
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(records, ensure_ascii=False, indent=2),
                      encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: str,
                       theorem_lib: Optional["TheoremLibrary"] = None,
                       ) -> "ExperienceLibrary":
        """Load library from JSON, skipping invalid entries."""
        lib = cls(theorem_lib=theorem_lib)
        p = Path(path)
        if not p.is_file():
            return lib
        try:
            records = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return lib
        for rec in records:
            scope_raw = rec.get("scope")
            if scope_raw:
                scope = MemoryScope.from_dict(scope_raw)
            else:
                scope = infer_default_scope(
                    exp_id=str(rec.get("id", "")),
                    domain=rec.get("domain", []),
                )
            exp = CodingExperience(
                id=rec.get("id", ""),
                title=rec.get("title", ""),
                domain=rec.get("domain", []),
                theorem_basis=set(rec.get("theorem_basis", [])),
                context=rec.get("context", ""),
                pattern=rec.get("pattern", ""),
                benchmarks=rec.get("benchmarks", {}),
                validity_start=rec.get("validity_start", 0.0),
                validity_end=rec.get("validity_end", float("inf")),
                supersedes=rec.get("supersedes"),
                scope=scope,
            )
            lib.add(exp, skip_validation=True)
        return lib

    def load_seed_if_empty(self) -> int:
        """Load seed experiences from bundled data if the library is empty."""
        if self._experiences:
            return 0
        count = 0
        for exp_dict in SEED_EXPERIENCES:
            exp = CodingExperience(**exp_dict)
            self.add(exp, skip_validation=True)
            count += 1
        return count


__all__ = [
    "CodingExperience",
    "ExperienceLibrary",
]
