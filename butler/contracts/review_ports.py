"""DevEngine review boundary contracts — structured code review ACL."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["v1"] = "v1"

ReviewSeverity = Literal["error", "warning", "info"]


class ReviewFinding(BaseModel):
    """Single deterministic or LLM-backed review finding."""

    model_config = ConfigDict(strict=True)

    severity: ReviewSeverity = "warning"
    rule_id: str = Field(default="", description="Rubric id e.g. RK-SIZE")
    file: str = ""
    line: int = 0
    message: str = ""
    evidence: str = ""


class DevReviewView(BaseModel):
    """Invariant review snapshot consumed by dev_loop / delegate gates."""

    model_config = ConfigDict(strict=True)

    passed: bool = True
    findings: list[ReviewFinding] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    schema_version: Literal["v1"] = SCHEMA_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


def dev_review_view_schema() -> dict[str, Any]:
    return DevReviewView.model_json_schema()


def dev_review_view_schema_json(*, indent: int = 2) -> str:
    return json.dumps(dev_review_view_schema(), ensure_ascii=False, indent=indent) + "\n"
