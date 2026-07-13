"""黑板 Pydantic schema 模型。

所有 Agent 写的 YAML 都按此 schema 校验。版本字段 `schema_version`
为 1 时是当前规约。
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


SCHEMA_VERSION = 1


class AgentEnum(str, Enum):
    CLAUDE_CODE = "claude-code"
    CURSOR = "cursor"
    CODEX = "codex"
    OPENCODE = "opencode"
    HUMAN = "human"


class SessionWindow(BaseModel):
    start: str  # ISO8601
    end: str | None = None  # 进行中可空

    @field_validator("start")
    @classmethod
    def _validate_iso(cls, v: str) -> str:
        # 宽松校验：含 T 与时区
        if "T" not in v:
            raise ValueError(f"session_window.start must be ISO8601 with T separator: {v!r}")
        return v


class ProducedItem(BaseModel):
    type: Literal["commit", "doc", "config", "test"]
    ref: str
    summary: str | None = None


class NextShiftRecommendation(BaseModel):
    agent: str  # 不强制枚举：留给未来的 Agent
    reason: str
    blocked_by: list[str] = Field(default_factory=list)


class ShiftCard(BaseModel):
    shift_id: str  # YYYY-MM-DD-<agent>-<NNN>
    agent: AgentEnum
    session_window: SessionWindow
    intent: str
    scope: list[str] = Field(min_length=1)
    read_at_start: list[str] = Field(min_length=1)
    produced: list[ProducedItem] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    next_shift_recommendation: NextShiftRecommendation | None = None
    claim_ref: str | None = None
    schema_version: Literal[1] = SCHEMA_VERSION


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class TaskStatus(str, Enum):
    OPEN = "open"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    DEFERRED = "deferred"


class BacklogRef(BaseModel):
    file: str
    anchor: str | None = None


class BacklogTask(BaseModel):
    id: str
    title: str
    priority: Priority
    status: TaskStatus
    claimed_by: str | None = None
    claim_ref: str | None = None
    notes: str | None = None
    refs: list[BacklogRef] = Field(default_factory=list)


class BacklogFile(BaseModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    last_updated: str
    tasks: list[BacklogTask]


class ClaimStatus(str, Enum):
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ABANDONED = "abandoned"
    HANDED_OFF = "handed_off"


class Claim(BaseModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    task_id: str
    claimed_by: str
    claimed_at: str  # ISO8601
    expected_close_at: str | None = None
    status: ClaimStatus
    handoff_to: str | None = None
    shift_refs: list[str] = Field(default_factory=list)
    notes: str | None = None