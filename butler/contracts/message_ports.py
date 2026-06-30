"""API message boundary contracts — per-message view before LLM transport (ACL subset)."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["v1"] = "v1"

ApiRole = Literal["system", "user", "assistant", "tool"]


class LoopApiMessageView(BaseModel):  # type: ignore[misc]
    """Minimal invariant view for one API-bound message (not full conversation state)."""

    model_config = ConfigDict(strict=True)

    role: ApiRole
    content: str = Field(default="", description="Normalized text content for API boundary")
    schema_version: Literal["v1"] = SCHEMA_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


def loop_api_message_view_schema() -> dict[str, Any]:
    """JSON Schema for CI drift check."""
    return cast(dict[str, Any], LoopApiMessageView.model_json_schema())


def loop_api_message_view_schema_json(*, indent: int = 2) -> str:
    return json.dumps(loop_api_message_view_schema(), ensure_ascii=False, indent=indent) + "\n"
