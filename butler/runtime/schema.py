"""Runtime job schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NotifyConfig:
    on_success: bool = True
    on_failure: bool = True
    max_summary_chars: int = 1200


@dataclass
class ApprovalConfig:
    required: bool = True
    expires_hours: int = 48


@dataclass
class JobDef:
    id: str
    description: str = ""
    mode: str = "readonly"  # readonly | mutating
    enabled: bool = True
    schedule: str = ""
    command: list[str] = field(default_factory=list)
    handler: str = ""
    timeout_seconds: int = 900
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)

    @property
    def is_readonly(self) -> bool:
        return (self.mode or "readonly").strip().lower() == "readonly"

    @property
    def is_builtin(self) -> bool:
        return bool((self.handler or "").strip().startswith("builtin:"))


@dataclass
class JobsFile:
    version: int
    project: str
    defaults: dict[str, Any]
    jobs: list[JobDef]
