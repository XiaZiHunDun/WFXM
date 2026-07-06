"""Manifest-driven MCP intent matching (L2 grounding router)."""

from __future__ import annotations

import re
from functools import lru_cache

from butler.env_parse import env_truthy
from butler.mcp.extension_manifest import IntentRule, load_intent_rules


@lru_cache(maxsize=1)
def _compiled_rules() -> list[tuple[IntentRule, list[re.Pattern[str]]]]:
    compiled: list[tuple[IntentRule, list[re.Pattern[str]]]] = []
    for rule in load_intent_rules():
        patterns: list[re.Pattern[str]] = []
        for raw in rule.patterns:
            try:
                patterns.append(re.compile(raw))
            except re.error:
                continue
        compiled.append((rule, patterns))
    return compiled


def intent_enabled(rule: IntentRule) -> bool:
    if rule.enabled_env:
        return bool(env_truthy(rule.enabled_env, default=rule.default_enabled))
    return bool(rule.default_enabled)


def matches_manifest_intent(
    text: str,
    *,
    kind: str,
    server_id: str = "",
) -> bool:
    raw = str(text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    want_kind = str(kind or "").strip()
    want_server = str(server_id or "").strip().lower()
    for rule, patterns in _compiled_rules():
        if rule.kind != want_kind:
            continue
        if want_server and rule.server_id.lower() != want_server:
            continue
        if not intent_enabled(rule):
            continue
        for pattern in patterns:
            if pattern.search(raw):
                return True
        if rule.fallback_keywords:
            lowered = raw.lower()
            hits = sum(
                1 for k in rule.fallback_keywords if k.lower() in lowered or k in raw
            )
            need = 2 if len(rule.fallback_keywords) >= 2 else 1
            if hits >= need:
                return True
    return False


def clear_intent_cache() -> None:
    _compiled_rules.cache_clear()
