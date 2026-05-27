"""Conversational test evaluation framework.

Provides ConversationRubric and assertion helpers for validating
real-LLM conversational responses against structured criteria.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConversationRubric:
    """Multi-level evaluation rubric for a single conversational turn."""

    # --- L1: structural assertions (hard-fail) ---
    expect_tool_called: str | None = None
    expect_any_tool_called: list[str] | None = None
    expect_tool_args_contain: dict[str, Any] | None = None
    expect_no_tool: bool = False
    expect_keywords: list[str] = field(default_factory=list)
    reject_keywords: list[str] = field(default_factory=list)

    # --- L2: soft / semantic assertions (warn-only) ---
    semantic_criteria: str = ""
    soft_keywords: list[str] = field(default_factory=list)

    # --- L3: meta constraints ---
    max_response_length: int = 2500
    max_latency_seconds: float = 60.0


@dataclass
class TurnResult:
    """Captured result of one conversational turn."""

    user_input: str
    response: str
    latency_seconds: float
    tool_events: list[dict[str, Any]]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def evaluate_turn(result: TurnResult, rubric: ConversationRubric) -> TurnResult:
    """Evaluate a TurnResult against a ConversationRubric, populating errors/warnings."""

    # tool call assertions
    called_tools = [e["tool"] for e in result.tool_events if e.get("ok")]

    if rubric.expect_tool_called:
        if rubric.expect_tool_called not in called_tools:
            result.errors.append(
                f"Expected tool '{rubric.expect_tool_called}' not called. "
                f"Called: {called_tools}"
            )

    if rubric.expect_any_tool_called:
        if not any(t in called_tools for t in rubric.expect_any_tool_called):
            result.errors.append(
                f"Expected one of {rubric.expect_any_tool_called} not called. "
                f"Called: {called_tools}"
            )

    if rubric.expect_no_tool:
        if called_tools:
            result.warnings.append(
                f"Expected no tool calls, but got: {called_tools}"
            )

    # tool argument assertions
    if rubric.expect_tool_args_contain and rubric.expect_tool_called:
        matching_events = [
            e for e in result.tool_events
            if e.get("tool") == rubric.expect_tool_called and e.get("ok")
        ]
        if matching_events:
            event = matching_events[0]
            arg_keys = set(event.get("arg_keys", []))
            for key in rubric.expect_tool_args_contain:
                if key not in arg_keys:
                    result.warnings.append(
                        f"Tool '{rubric.expect_tool_called}' missing arg key '{key}'. "
                        f"Present: {arg_keys}"
                    )

    # keyword assertions (case-insensitive)
    resp_lower = result.response.lower()
    for kw in rubric.expect_keywords:
        if kw.lower() not in resp_lower:
            result.errors.append(f"Expected keyword '{kw}' not found in response")

    for kw in rubric.reject_keywords:
        if kw.lower() in resp_lower:
            result.errors.append(f"Rejected keyword '{kw}' found in response")

    for kw in rubric.soft_keywords:
        if kw.lower() not in resp_lower:
            result.warnings.append(f"Soft keyword '{kw}' not found in response")

    # meta constraints
    if len(result.response) > rubric.max_response_length:
        result.warnings.append(
            f"Response length {len(result.response)} exceeds max {rubric.max_response_length}"
        )

    if result.latency_seconds > rubric.max_latency_seconds:
        result.warnings.append(
            f"Latency {result.latency_seconds:.1f}s exceeds max {rubric.max_latency_seconds}s"
        )

    return result


def assert_turn_passed(result: TurnResult) -> None:
    """Raise AssertionError if any hard errors exist. Log warnings."""
    for w in result.warnings:
        logger.warning("[CONV-WARN] %s | input=%r", w, result.user_input)
    if result.errors:
        detail = "\n  ".join(result.errors)
        raise AssertionError(
            f"Conversational turn failed for input: {result.user_input!r}\n"
            f"Response (first 300): {result.response[:300]!r}\n"
            f"Errors:\n  {detail}"
        )


def format_report(results: list[TurnResult]) -> str:
    """Format a human-readable report of all evaluated turns."""
    lines = [f"=== Conversational Test Report ({len(results)} turns) ===\n"]
    for i, r in enumerate(results, 1):
        status = "PASS" if not r.errors else "FAIL"
        tools = [e["tool"] for e in r.tool_events if e.get("ok")]
        lines.append(f"Turn {i}: [{status}] {r.user_input!r}")
        lines.append(f"  Response (first 100): {r.response[:100]!r}")
        lines.append(f"  Tools called: {tools}")
        lines.append(f"  Latency: {r.latency_seconds:.1f}s")
        if r.errors:
            for e in r.errors:
                lines.append(f"  ERROR: {e}")
        if r.warnings:
            for w in r.warnings:
                lines.append(f"  WARN: {w}")
        lines.append("")
    passed = sum(1 for r in results if not r.errors)
    lines.append(f"Result: {passed}/{len(results)} passed")
    return "\n".join(lines)
