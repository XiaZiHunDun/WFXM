"""Classify MCP tools as readonly / mutating / network."""

from __future__ import annotations

import re

_MUTATING_VERBS = re.compile(
    r"\b(write|create|delete|remove|update|patch|execute|run|insert|drop|send|post|put|merge|commit|push)\b",
    re.I,
)


def classify_tool(
    original_name: str,
    description: str = "",
    *,
    config_override: str = "",
) -> str:
    override = str(config_override or "").strip().lower()
    if override in ("readonly", "mutating", "network"):
        return override
    text = f"{original_name} {description}"
    if _MUTATING_VERBS.search(text):
        return "mutating"
    if re.search(r"\b(fetch|http|request|browse|search_web)\b", text, re.I):
        return "network"
    return "readonly"


def is_mutating_classification(classification: str) -> bool:
    return str(classification or "").strip().lower() in ("mutating", "network")
