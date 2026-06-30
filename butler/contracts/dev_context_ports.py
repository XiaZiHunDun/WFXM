"""DevEngine boundary contracts — verify / transition payload ACL (P3)."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["v1"] = "v1"


class DevVerifyView(BaseModel):
    """Invariant verify snapshot consumed by dev_loop after ACL."""

    model_config = ConfigDict(strict=True)

    status: str = Field(default="UNKNOWN", description="PASS|FAIL|TIMEOUT|SKIP|UNKNOWN")
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    output_tail: str = ""
    command: str = ""
    exit_code: int | None = None
    elapsed_seconds: float = 0.0
    schema_version: Literal["v1"] = SCHEMA_VERSION
    metadata: dict[str, Any] = Field(default_factory=dict)


def dev_verify_view_schema() -> dict[str, Any]:
    return DevVerifyView.model_json_schema()


def dev_verify_view_schema_json(*, indent: int = 2) -> str:
    return json.dumps(dev_verify_view_schema(), ensure_ascii=False, indent=indent) + "\n"
