"""DevEngine state boundary contracts — Loop-facing dev state snapshot (ACL)."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["v1"] = "v1"

_VALID_PHASES = frozenset(
    {"PLAN", "LOCATE", "EDIT", "VERIFY", "FIX", "DONE", "STUCK", "REVIEW"}
)


class LoopDevStateView(BaseModel):  # type: ignore[misc]
    """Invariant dev-loop snapshot for delegate gates / reporting after ACL."""

    model_config = ConfigDict(strict=True)

    phase: str = Field(default="PLAN", description="DevPhase value")
    verify_passed: bool | None = None
    review_passed: bool | None = None
    edits: int = 0
    fixes: int = 0
    iterations: int = 0
    is_terminal: bool = False
    schema_version: Literal["v1"] = SCHEMA_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


def loop_dev_state_view_schema() -> dict[str, Any]:
    return cast(dict[str, Any], LoopDevStateView.model_json_schema())


def loop_dev_state_view_schema_json(*, indent: int = 2) -> str:
    return json.dumps(loop_dev_state_view_schema(), ensure_ascii=False, indent=indent) + "\n"


def normalize_dev_phase(raw: Any) -> str:
    text = str(raw or "PLAN").strip().upper()
    return text if text in _VALID_PHASES else "PLAN"
