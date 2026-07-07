"""Agent report datatypes (shared by generator and acceptance_card)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Change:
    file: str
    action: str  # "created" | "modified" | "deleted"
    description: str


@dataclass
class AgentReport:
    headline: str = ""
    changes: list[Change] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    summary: str = ""
    success: bool = True
    task_preview: str = ""
    task_id: str = ""
    child_session_key: str = ""
    iterations: int = 0
    tool_calls: int = 0
    tokens_used: int = 0
    elapsed_seconds: float = 0.0
    task_created_at: str = ""
    task_completed_at: str = ""
    failed_steps: list[str] = field(default_factory=list)
    step_outcomes: dict[str, str] = field(default_factory=dict)
    structured_output: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "changes": [
                {"file": c.file, "action": c.action, "description": c.description}
                for c in self.changes
            ],
            "decisions": list(self.decisions),
            "issues": list(self.issues),
            "summary": self.summary,
            "success": self.success,
            "task_preview": self.task_preview,
            "task_id": self.task_id,
            "child_session_key": self.child_session_key,
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "tokens_used": self.tokens_used,
            "elapsed_seconds": self.elapsed_seconds,
            "task_created_at": self.task_created_at,
            "task_completed_at": self.task_completed_at,
            "failed_steps": list(self.failed_steps),
            "step_outcomes": dict(self.step_outcomes),
            "structured_output": dict(self.structured_output),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentReport:
        raw = dict(data or {})
        changes_raw = raw.pop("changes", []) or []
        changes: list[Change] = []
        for item in changes_raw:
            if isinstance(item, Change):
                changes.append(item)
                continue
            if not isinstance(item, dict):
                continue
            changes.append(
                Change(
                    file=str(item.get("file", "") or ""),
                    action=str(item.get("action", "") or ""),
                    description=str(item.get("description", item.get("desc", "")) or ""),
                )
            )
        return cls(
            headline=str(raw.get("headline", "") or ""),
            changes=changes,
            decisions=[str(x) for x in (raw.get("decisions") or [])],
            issues=[str(x) for x in (raw.get("issues") or [])],
            summary=str(raw.get("summary", "") or ""),
            success=bool(raw.get("success", True)),
            task_preview=str(raw.get("task_preview", "") or ""),
            task_id=str(raw.get("task_id", "") or ""),
            child_session_key=str(raw.get("child_session_key", "") or ""),
            iterations=int(raw.get("iterations") or 0),
            tool_calls=int(raw.get("tool_calls") or 0),
            tokens_used=int(raw.get("tokens_used") or 0),
            elapsed_seconds=float(raw.get("elapsed_seconds") or 0.0),
            task_created_at=str(raw.get("task_created_at", "") or ""),
            task_completed_at=str(raw.get("task_completed_at", "") or ""),
            failed_steps=[str(x) for x in (raw.get("failed_steps") or [])],
            step_outcomes={
                str(k): str(v)
                for k, v in (raw.get("step_outcomes") or {}).items()
                if isinstance(raw.get("step_outcomes"), dict)
            },
            structured_output=dict(raw.get("structured_output") or {}),
        )


__all__ = ["AgentReport", "Change"]
