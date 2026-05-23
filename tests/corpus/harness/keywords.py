"""Keyword rubric assertions for agent_loop corpus cases."""

from __future__ import annotations

from typing import Any

from butler.transport.types import NormalizedResponse, Usage


def keyword_groups(rules: dict[str, Any]) -> list[list[str]]:
    groups: list[list[str]] = []
    for key in sorted(rules.keys()):
        if not key.startswith("must_contain_any"):
            continue
        raw = rules.get(key) or []
        if raw:
            groups.append([str(x) for x in raw])
    return groups


def assert_keywords(text: str, rules: dict[str, Any]) -> None:
    body = text or ""
    lower = body.lower()
    for kw in rules.get("must_contain") or []:
        token = str(kw)
        assert token.lower() in lower or token in body, f"missing required: {token!r}"
    for group in keyword_groups(rules):
        assert any(
            k.lower() in lower or k in body for k in group
        ), f"none matched in group: {group!r}"
    for bad in rules.get("must_not_contain") or []:
        token = str(bad)
        assert token.lower() not in lower, f"forbidden phrase present: {token!r}"


def build_canonical_answer(case: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in case.get("must_contain") or []:
        parts.append(str(item))
    for group in keyword_groups(case):
        parts.extend(group)
    for turn in case.get("turns") or []:
        for item in turn.get("must_contain") or []:
            parts.append(str(item))
        for group in keyword_groups(turn):
            parts.extend(group)
    title = case.get("title") or case.get("id", "")
    return f"【{title}】\n" + "\n".join(parts)


def canonical_response(text: str) -> NormalizedResponse:
    return NormalizedResponse(
        content=text,
        usage=Usage(prompt_tokens=10, completion_tokens=80, total_tokens=90),
    )
