"""Workflow step variable pool (Dify VariablePool / Langflow FlowTool subset)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


@dataclass
class WorkflowVariablePool:
    """Maps ``step_id`` or ``step_id.key`` to string values."""

    values: dict[str, str] = field(default_factory=dict)

    def set_step_output(self, step_id: str, text: str, *, keys: list[str] | None = None) -> None:
        sid = str(step_id or "").strip()
        if not sid:
            return
        body = (text or "").strip()
        self.values[sid] = body[:4000]
        for key in keys or ("output", "result", "summary"):
            self.values[f"{sid}.{key}"] = body[:4000]

    def get(self, ref: str) -> str:
        key = str(ref or "").strip()
        if not key:
            return ""
        if key in self.values:
            return self.values[key]
        if "." not in key:
            return self.values.get(key, "")
        return ""

    def interpolate(self, template: str) -> str:
        if not template or "{{" not in template:
            return template

        def _repl(match: re.Match[str]) -> str:
            ref = match.group(1)
            val = self.get(ref)
            return val if val else match.group(0)

        return _VAR_RE.sub(_repl, template)


def extract_output_keys(step_raw: dict[str, Any]) -> list[str]:
    raw = step_raw.get("outputs") or step_raw.get("output_keys")
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    if isinstance(raw, list):
        return [str(k).strip() for k in raw if str(k).strip()]
    return ["output"]
