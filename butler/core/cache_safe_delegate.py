"""Share static system-prefix with parent loop for delegate prompt-cache alignment."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from butler.env_parse import env_truthy

_DEFAULT_SHARED_CHARS = 4096
_DEFAULT_MESSAGES_PREFIX_CHARS = 2048


def cache_safe_delegate_enabled() -> bool:
    return env_truthy("BUTLER_CACHE_SAFE_DELEGATE", default=True)


def shared_prefix_max_chars() -> int:
    try:
        return max(512, int(os.getenv("BUTLER_CACHE_SAFE_SHARED_CHARS", "") or _DEFAULT_SHARED_CHARS))
    except ValueError:
        return _DEFAULT_SHARED_CHARS


def messages_prefix_max_chars() -> int:
    try:
        return max(
            256,
            int(os.getenv("BUTLER_CACHE_SAFE_MESSAGES_CHARS", "") or _DEFAULT_MESSAGES_PREFIX_CHARS),
        )
    except ValueError:
        return _DEFAULT_MESSAGES_PREFIX_CHARS


def system_prompt_fingerprint(text: str) -> str:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return digest[:16]


def tools_schema_fingerprint(tools: list[dict] | None) -> str:
    if not tools:
        return "none"
    try:
        blob = json.dumps(tools, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        blob = str(tools)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def messages_prefix_fingerprint(messages: list[dict] | None) -> str:
    if not messages:
        return "none"
    parts: list[str] = []
    budget = messages_prefix_max_chars()
    used = 0
    for msg in messages:
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")[:500]
        chunk = f"{role}:{content}"
        if used + len(chunk) > budget:
            break
        parts.append(chunk)
        used += len(chunk)
    blob = "\n".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def extract_shared_prefix(parent_system: str, *, max_chars: int | None = None) -> str:
    limit = max_chars if max_chars is not None else shared_prefix_max_chars()
    return (parent_system or "").strip()[:limit]


def compute_cache_safe_bundle(
    *,
    parent_system: str,
    child_system: str,
    tools: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> dict[str, Any]:
    prefix = extract_shared_prefix(parent_system)
    return {
        "shared_prefix_chars": len(prefix),
        "parent_system_fingerprint": system_prompt_fingerprint(parent_system),
        "child_system_fingerprint": system_prompt_fingerprint(child_system),
        "tools_fingerprint": tools_schema_fingerprint(tools),
        "messages_prefix_fingerprint": messages_prefix_fingerprint(messages),
        "cache_safe_v2": True,
    }


def apply_cache_safe_system_prompt(
    parent_system: str,
    child_system: str,
    *,
    tools: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> str:
    """Prepend parent's cacheable prefix when child does not already include it."""
    if not cache_safe_delegate_enabled():
        return child_system
    prefix = extract_shared_prefix(parent_system)
    if not prefix:
        return child_system
    child = (child_system or "").strip()
    if prefix in child:
        return child
    tools_fp = tools_schema_fingerprint(tools)
    msgs_fp = messages_prefix_fingerprint(messages)
    return (
        f"{prefix}\n\n"
        "[DELEGATE — shared prefix matches parent for prompt cache]\n"
        f"[cache-tools={tools_fp} cache-msgs={msgs_fp}]\n\n"
        f"{child}"
    )


def delegate_diagnostics(
    parent_system: str,
    child_system: str,
    *,
    tools: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> dict[str, Any]:
    bundle = compute_cache_safe_bundle(
        parent_system=parent_system,
        child_system=child_system,
        tools=tools,
        messages=messages,
    )
    bundle["cache_safe_delegate"] = True
    return bundle
