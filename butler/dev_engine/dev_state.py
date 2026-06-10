"""DevState — Development state machine data structures.

Formal model from v4-dev-engine-theory.md §2.1:
  DevState = (Files, Diagnostics, VerifyResult, EditHistory, SearchContext)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DevPhase(str, Enum):
    """Development loop states (Definition D6)."""

    PLAN = "PLAN"
    LOCATE = "LOCATE"
    EDIT = "EDIT"
    VERIFY = "VERIFY"
    FIX = "FIX"
    DONE = "DONE"
    STUCK = "STUCK"
    REVIEW = "REVIEW"


class VerifyStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    SKIP = "SKIP"
    UNKNOWN = "UNKNOWN"


class DiagSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    """Structured diagnostic entry (DD3)."""

    file: str
    line: int
    column: int = 0
    severity: DiagSeverity = DiagSeverity.ERROR
    message: str = ""
    source: str = ""
    rule: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "severity": self.severity.value,
            "message": self.message,
            "source": self.source,
            "rule": self.rule,
        }


@dataclass
class EditRecord:
    """Single edit with undo info (Definition D5)."""

    operation: str  # write | patch | delete | create
    path: str
    timestamp: float = field(default_factory=time.time)
    original_content: str | None = None
    new_content: str | None = None
    patch_old: str | None = None
    patch_new: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "operation": self.operation,
            "path": self.path,
            "timestamp": self.timestamp,
        }
        if self.patch_old is not None:
            d["patch_old"] = self.patch_old[:200]
        if self.patch_new is not None:
            d["patch_new"] = self.patch_new[:200]
        return d


@dataclass
class SearchHit:
    """Code search result entry."""

    path: str
    range_start: int = 0
    range_end: int = 0
    relevance: float = 1.0
    snippet: str = ""


@dataclass
class VerifyResult:
    """Result of a verification step."""

    status: VerifyStatus = VerifyStatus.UNKNOWN
    diagnostics: list[Diagnostic] = field(default_factory=list)
    command: str = ""
    elapsed_seconds: float = 0.0
    exit_code: int | None = None

    @property
    def passed(self) -> bool:
        return self.status == VerifyStatus.PASS

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == DiagSeverity.ERROR)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "error_count": self.error_count,
            "diagnostics": [d.to_dict() for d in self.diagnostics[:20]],
            "command": self.command,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "exit_code": self.exit_code,
        }


@dataclass
class CodingKnowledgeSummary:
    """Lightweight summary of coding knowledge layer activation (CD7).

    Stored in DevState to avoid importing the full coding_knowledge module
    at the data-structure level.
    """

    mode: str = ""  # "experience_guided" | "theorem_only" | ""
    activated_theorem_ids: list[str] = field(default_factory=list)
    activated_elements: list[str] = field(default_factory=list)
    experience_id: str = ""
    experience_title: str = ""
    violated_theorems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"mode": self.mode}
        if self.activated_theorem_ids:
            d["theorems"] = self.activated_theorem_ids
        if self.activated_elements:
            d["elements"] = self.activated_elements
        if self.experience_id:
            d["experience"] = {"id": self.experience_id,
                               "title": self.experience_title}
        if self.violated_theorems:
            d["violated"] = self.violated_theorems
        return d


@dataclass
class DevState:
    """Development state for a single task (Definition D1).

    Tracks files touched, diagnostics, verification results,
    edit history (for rollback), search context, and coding knowledge.
    """

    phase: DevPhase = DevPhase.PLAN
    task_description: str = ""
    edit_history: list[EditRecord] = field(default_factory=list)
    verify_result: VerifyResult = field(default_factory=VerifyResult)
    search_context: list[SearchHit] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    coding_knowledge: CodingKnowledgeSummary = field(
        default_factory=CodingKnowledgeSummary)
    fix_count: int = 0
    iteration: int = 0
    max_fix_rounds: int = 3
    max_iterations: int = 24
    created_at: float = field(default_factory=time.time)

    @property
    def is_terminal(self) -> bool:
        return self.phase in (DevPhase.DONE, DevPhase.STUCK)

    def record_edit(self, record: EditRecord) -> None:
        self.edit_history.append(record)

    def advance_phase(self, new_phase: DevPhase) -> None:
        self.phase = new_phase
        self.iteration += 1

    def record_fix_attempt(self) -> bool:
        """Record a fix attempt. Returns False if K_max exceeded."""
        self.fix_count += 1
        return self.fix_count <= self.max_fix_rounds

    def should_terminate(self) -> bool:
        """Check if dev loop should terminate (DT2 enforcement)."""
        if self.iteration >= self.max_iterations:
            return True
        if self.fix_count > self.max_fix_rounds:
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        d = {
            "phase": self.phase.value,
            "task": self.task_description[:200] if self.task_description else "",
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "fix_count": self.fix_count,
            "max_fix_rounds": self.max_fix_rounds,
            "edit_count": len(self.edit_history),
            "recent_edits": [e.to_dict() for e in self.edit_history[-5:]],
            "verify": self.verify_result.to_dict(),
            "search_hits": len(self.search_context),
            "diagnostic_count": len(self.diagnostics),
        }
        if self.coding_knowledge.mode:
            d["coding_knowledge"] = self.coding_knowledge.to_dict()
        return d

    def summary(self) -> str:
        lines = [
            f"开发状态: {self.phase.value}",
            f"迭代: {self.iteration}/{self.max_iterations}",
            f"修复: {self.fix_count}/{self.max_fix_rounds}",
            f"编辑: {len(self.edit_history)} 次",
            f"验证: {self.verify_result.status.value}",
        ]
        if self.diagnostics:
            errs = sum(1 for d in self.diagnostics if d.severity == DiagSeverity.ERROR)
            lines.append(f"诊断: {errs} errors, {len(self.diagnostics) - errs} others")
        if self.coding_knowledge.mode:
            lines.append(f"知识层: {self.coding_knowledge.mode}"
                         f" ({len(self.coding_knowledge.activated_theorem_ids)} 定理)")
        return " | ".join(lines)
