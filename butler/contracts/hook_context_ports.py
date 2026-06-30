"""Hook context boundary contracts — prompt / diagnostics hook ACL (P2)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["v1"] = "v1"


class HookContextView(BaseModel):
    """Invariant view for hook additionalContext before prompt / diagnostics."""

    model_config = ConfigDict(strict=True)

    content: str = Field(default="", description="Unified hook context text")
    schema_version: Literal["v1"] = SCHEMA_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


def hook_context_view_schema() -> dict[str, Any]:
    return HookContextView.model_json_schema()


def hook_context_view_schema_json(*, indent: int = 2) -> str:
    return json.dumps(hook_context_view_schema(), ensure_ascii=False, indent=indent) + "\n"
