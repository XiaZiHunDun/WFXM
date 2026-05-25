"""Shrink tool schemas when count exceeds threshold (LangChain ToolSelector subset)."""

from __future__ import annotations

import os
import re
from typing import Iterable

from butler.env_parse import env_truthy

_CORE_TOOLS = frozenset({
    "read_file",
    "search_files",
    "list_directory",
    "delegate_task",
    "butler_recall",
    "search_transcript",
    "run_workflow",
})


def tool_selector_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_SELECTOR", default=True)


def tool_selector_threshold() -> int:
    try:
        return max(4, min(40, int(os.getenv("BUTLER_TOOL_SELECTOR_THRESHOLD", "12"))))
    except ValueError:
        return 12


def _tool_name(defn: dict) -> str:
    fn = defn.get("function") if isinstance(defn.get("function"), dict) else {}
    return str(fn.get("name") or defn.get("name") or "").strip()


def _tool_text(defn: dict) -> str:
    fn = defn.get("function") if isinstance(defn.get("function"), dict) else {}
    parts = [str(fn.get("name") or ""), str(fn.get("description") or "")]
    return " ".join(parts).lower()


def _score_tool(defn: dict, *, keywords: set[str]) -> int:
    if not keywords:
        return 0
    text = _tool_text(defn)
    score = 0
    for kw in keywords:
        if kw in text:
            score += 2
        if kw in _tool_name(defn):
            score += 3
    return score


def _keywords_from_context(*, user_hint: str = "", role: str = "") -> set[str]:
    blob = f"{user_hint} {role}".lower()
    return {w for w in re.split(r"[^\w\u4e00-\u9fff]+", blob) if len(w) >= 2}


def select_tools_for_context(
    tools: list[dict],
    *,
    user_hint: str = "",
    role: str = "",
    threshold: int | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Return (selected_tools, diagnostics)."""
    diag: dict[str, int] = {
        "tool_selector_input": len(tools),
        "tool_selector_output": len(tools),
    }
    if not tool_selector_enabled() or not tools:
        return list(tools), diag

    cap = threshold if threshold is not None else tool_selector_threshold()

    try:
        from butler.core.tool_recall_bm25 import (
            select_tools_with_bm25,
            tool_recall_bm25_enabled,
        )

        if tool_recall_bm25_enabled() and len(tools) > cap:
            return select_tools_with_bm25(tools, user_hint=user_hint or role, top_k=cap)
    except Exception:
        pass

    if len(tools) <= cap:
        return list(tools), diag

    keywords = _keywords_from_context(user_hint=user_hint, role=role)
    ranked: list[tuple[int, int, dict]] = []
    for idx, defn in enumerate(tools):
        name = _tool_name(defn)
        base = 100 if name in _CORE_TOOLS else 0
        ranked.append((base + _score_tool(defn, keywords=keywords), idx, defn))

    ranked.sort(key=lambda t: (-t[0], t[1]))
    chosen: list[dict] = []
    seen: set[str] = set()
    for _, _, defn in ranked:
        name = _tool_name(defn)
        if name in seen:
            continue
        chosen.append(defn)
        seen.add(name)
        if len(chosen) >= cap:
            break

    for _, _, defn in ranked:
        name = _tool_name(defn)
        if name in _CORE_TOOLS and name not in seen:
            chosen.append(defn)
            seen.add(name)

    diag["tool_selector_output"] = len(chosen)
    diag["tool_selector_dropped"] = max(0, len(tools) - len(chosen))
    return chosen, diag
