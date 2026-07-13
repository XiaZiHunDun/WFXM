"""黑板 Pydantic schema 模型。

所有 Agent 写的 YAML 都按此 schema 校验。版本字段 `schema_version`
为 1 时是当前规约。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


SCHEMA_VERSION = 1


def _to_iso_string(v: str | datetime) -> str:
    """接受 ISO8601 字符串或 datetime，统一规范化为字符串。

    PyYAML 自动把 `2026-07-13T09:00:00+08:00` 解析为 datetime，
    所以必须容忍两种输入。
    """
    if isinstance(v, datetime):
        # 保留时区；若 naive 当作 UTC
        if v.tzinfo is None:
            return v.isoformat()
        return v.isoformat()
    if "T" not in v:
        raise ValueError(f"must be ISO8601 with T separator: {v!r}")
    return v


class AgentEnum(str, Enum):
    CLAUDE_CODE = "claude-code"
    CURSOR = "cursor"
    CODEX = "codex"
    OPENCODE = "opencode"
    HUMAN = "human"


class SessionWindow(BaseModel):
    start: str  # ISO8601（写盘前已规范化）
    end: str | None = None  # 进行中可空

    @field_validator("start", mode="before")
    @classmethod
    def _validate_start(cls, v: str | datetime) -> str:
        return _to_iso_string(v)

    @field_validator("end", mode="before")
    @classmethod
    def _validate_end(cls, v: str | datetime | None) -> str | None:
        if v is None:
            return None
        return _to_iso_string(v)


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

    @field_validator("last_updated", mode="before")
    @classmethod
    def _validate_last_updated(cls, v: str | datetime) -> str:
        return _to_iso_string(v)


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

    @field_validator("claimed_at", "expected_close_at", mode="before")
    @classmethod
    def _validate_iso_optional(cls, v: str | datetime | None) -> str | None:
        if v is None:
            return None
        return _to_iso_string(v)