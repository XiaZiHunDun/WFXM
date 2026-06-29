"""Compaction boundary contracts — Loop-facing compaction view (ACL)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["v1"] = "v1"


class LoopCompactionView(BaseModel):
    """Invariant view consumed by ContextPipeline / AgentLoop after ACL."""

    model_config = ConfigDict(strict=True)

    content: str = Field(default="", description="Unified compaction text for summary/anchors")
    schema_version: Literal["v1"] = SCHEMA_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


def loop_compaction_view_schema() -> dict[str, Any]:
    """JSON Schema for CI drift check."""
    return LoopCompactionView.model_json_schema()


def loop_compaction_view_schema_json(*, indent: int = 2) -> str:
    return json.dumps(loop_compaction_view_schema(), ensure_ascii=False, indent=indent) + "\n"
