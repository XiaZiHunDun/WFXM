"""Memory prefetch boundary contracts — Loop-facing memory injection view (ACL)."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["v1"] = "v1"


class LoopMemoryView(BaseModel):  # type: ignore[misc]
    """Invariant view consumed by memory prefetch / pre_llm_transform after ACL."""

    model_config = ConfigDict(strict=True)

    content: str = Field(default="", description="Unified memory text for injection")
    schema_version: Literal["v1"] = SCHEMA_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


def loop_memory_view_schema() -> dict[str, Any]:
    """JSON Schema for CI drift check."""
    return cast(dict[str, Any], LoopMemoryView.model_json_schema())


def loop_memory_view_schema_json(*, indent: int = 2) -> str:
    return json.dumps(loop_memory_view_schema(), ensure_ascii=False, indent=indent) + "\n"
