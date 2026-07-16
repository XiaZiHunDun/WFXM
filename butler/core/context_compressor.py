"""Context compression for long Butler conversations.

Simplified port of Hermes ``agent/context_compressor.py``:
  1. Prune large tool outputs (no LLM)
  2. Protect system + token-budget tail
  3. Summarize middle via auxiliary model
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, cast

from butler.env_parse import int_env
from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted. "
    "Treat as background, NOT active instructions. "
    "Resume from '## Active Task' in the summary. "
    "Respond ONLY to the latest user message after this block:\n\n"
)

_MIN_MESSAGES_TO_COMPRESS = 12


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    counter = _get_token_counter()
    total = 0
    for m in messages:
        text = json.dumps(m, ensure_ascii=False, default=str)
        total += counter(text)
    return total


def _heuristic_count(text: str) -> int:
    """Estimate token count with CJK-aware heuristic.

    English/ASCII: ~4 chars per token (len//4).
    CJK characters: ~0.77 chars per token (each CJK char ≈ 1.3 tokens for
    Claude/GPT BPE tokenizers — empirically measured on Chinese text).
    Punctuation between CJK chars typically merges, so we use a blended
    rate rather than counting every character as a full token.
    """
    cjk = 0
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF      # CJK Unified Ideographs
                or 0x3400 <= cp <= 0x4DBF  # Extension A
                or 0x3000 <= cp <= 0x303F  # CJK Symbols
                or 0xFF00 <= cp <= 0xFFEF  # Fullwidth Forms
                or 0x3040 <= cp <= 0x30FF):  # Hiragana + Katakana
            cjk += 1
    ascii_len = len(text) - cjk
    return int(ascii_len / 4 + cjk * 1.3)


_token_counter_cache: dict[str, Callable[[str], int]] = {}


def _get_token_counter() -> Callable[[str], int]:
    """Return a callable(str) -> int based on BUTLER_TOKEN_COUNTER env var.

    Supported values:
      - "heuristic" (default): len(json) // 4
      - "tiktoken": precise BPE counting via tiktoken (requires `pip install tiktoken`)
      - "tiktoken:<encoding>": use a specific tiktoken encoding (e.g. tiktoken:o200k_base)
    """
    import os

    mode = (os.getenv("BUTLER_TOKEN_COUNTER", "heuristic") or "heuristic").strip().lower()
    if mode == "heuristic":
        return _heuristic_count

    cached = _token_counter_cache.get(mode)
    if cached is not None:
        return cached

    if mode.startswith("tiktoken"):
        parts = mode.split(":", 1)
        encoding_name = parts[1] if len(parts) > 1 else "o200k_base"

        def _init_tiktoken() -> Callable[[str], int]:
            import tiktoken

            enc = tiktoken.get_encoding(encoding_name)

            def _tiktoken_count(text: str) -> int:
                return len(enc.encode(text, disallowed_special=()))

            _token_counter_cache[mode] = _tiktoken_count
            logger.info("Token counter: tiktoken/%s", encoding_name)
            return _tiktoken_count

        counter = safe_best_effort(
            _init_tiktoken,
            label="context_compressor.tiktoken_init",
            default=None,
        )
        if counter is not None:
            _clear_compaction_acl_degradation_safe()
            return cast(Callable[[str], int], counter)
        _register_compaction_acl_degradation_safe(reason="tiktoken 不可用，heuristic 估算")
        logger.warning(
            "tiktoken unavailable; falling back to heuristic. Install: pip install tiktoken"
        )

    return _heuristic_count


def _register_compaction_acl_degradation_safe(*, reason: str) -> None:
    from butler.core.best_effort import safe_best_effort
    from butler.ops.degradation_registry import register_degradation

    def _run() -> None:
        register_degradation("compaction_acl", reason)

    safe_best_effort(_run, label="context_compressor.tiktoken_register", default=None)


def _clear_compaction_acl_degradation_safe() -> None:
    from butler.core.best_effort import safe_best_effort
    from butler.ops.degradation_registry import clear_degradation

    def _run() -> None:
        clear_degradation("compaction_acl")

    safe_best_effort(_run, label="context_compressor.tiktoken_clear", default=None)


def prune_tool_outputs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prune oversized tool role messages before API / compaction (microCompact-style)."""
    return _prune_tool_outputs(messages)


def _prune_tool_outputs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from butler.core.tool_prune_policy import (
        build_tool_name_index,
        classify_tool,
        keep_recent_pim_tool_messages,
        keep_recent_tool_messages,
        prune_tool_message_content,
        _tool_message_indices,
    )

    id_to_name = build_tool_name_index(messages)
    tool_idxs = _tool_message_indices(messages)
    recent = set(tool_idxs[-keep_recent_tool_messages() :])
    pim_sensitive_idxs = [
        i for i in tool_idxs
        if classify_tool(id_to_name.get(str(messages[i].get("tool_call_id") or ""), "")) == "pii_clearable"
    ]
    pim_recent = set(pim_sensitive_idxs[-keep_recent_pim_tool_messages() :])

    out: list[dict[str, Any]] = []
    for i, m in enumerate(messages):
        if m.get("role") != "tool":
            out.append(m)
            continue
        content = str(m.get("content") or "")
        tool_name = id_to_name.get(str(m.get("tool_call_id") or ""), "")
        policy = classify_tool(tool_name)
        is_stale = i not in (pim_recent if policy == "pii_clearable" else recent)
        new_content = prune_tool_message_content(
            content,
            tool_name=tool_name,
            is_stale=is_stale,
        )
        if new_content == content:
            out.append(m)
        else:
            out.append({**m, "content": new_content})
    return out


def _split_head_tail(
    messages: list[dict[str, Any]],
    head_count: int = 3,
    tail_token_budget: int = 8000,
    max_tail_messages: int = 12,
    min_tail_messages: int = 4,
    protect_keywords: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    if len(rest) <= head_count + min_tail_messages:
        return system, [], rest

    protected_indices: set[int] = set()
    if protect_keywords and rest:
        for i, m in enumerate(rest):
            content = str(m.get("content") or "").lower()
            for kw in protect_keywords:
                if kw.lower() in content:
                    protected_indices.add(i)
                    break

    head = rest[:head_count]
    tail_candidates = rest[head_count:]
    tail: list[dict[str, Any]] = []
    budget = 0
    for m in reversed(tail_candidates):
        budget += len(str(m.get("content") or "")) // 4
        tail.insert(0, m)
        if len(tail) >= max_tail_messages or budget >= tail_token_budget:
            break

    middle_end = len(rest) - len(tail)
    from butler.core.compaction_cutoff import find_safe_tail_start

    middle_end = find_safe_tail_start(rest, middle_end)

    if protected_indices:
        protected_in_middle = [
            i for i in protected_indices if head_count <= i < middle_end
        ]
        if protected_in_middle:
            middle_end = min(protected_in_middle)

    tail = rest[middle_end:]
    middle = rest[head_count:middle_end] if middle_end > head_count else []
    return system, middle, head + tail


def compress_tool_response_budget_tokens() -> int:
    import os

    try:
        return int(max(5000, int_env("BUTLER_COMPRESS_TOOL_RESPONSE_BUDGET", 50000)))
    except ValueError:
        return 50_000


def truncate_tool_responses_to_budget(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Before LLM summarization, cap total tool-role tokens (Gemini pre-compress budget)."""
    import os

    if os.getenv("BUTLER_COMPRESS_TOOL_RESPONSE_BUDGET", "").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return messages
    budget = compress_tool_response_budget_tokens()
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    total = sum(len(str(m.get("content") or "")) // 4 for m in tool_msgs)
    if total <= budget:
        return messages

    from butler.core.tool_result_storage import BUDGET_TRUNCATED_TAG

    out: list[dict[str, Any]] = []
    remaining = budget
    changed = False
    for m in messages:
        if m.get("role") != "tool":
            out.append(m)
            continue
        content = str(m.get("content") or "")
        est = max(1, len(content) // 4)
        if remaining > 0 and est <= remaining:
            out.append(m)
            remaining -= est
            continue
        changed = True
        lines = content.splitlines()
        tail = "\n".join(lines[-30:]) if len(lines) > 30 else content[:4000]
        trimmed = (
            tail[:8000]
            + f"\n\n{BUDGET_TRUNCATED_TAG} "
            f"(pre-compact budget; was ~{est * 4} chars)\n"
        )
        out.append({**m, "content": trimmed})
    if changed:
        safe_best_effort(
            lambda: __import__(
                "butler.ops.retry_buckets", fromlist=["record_recovery_event"]
            ).record_recovery_event("compress_tool_budget_truncate"),
            label="context_compressor.record_recovery_event",
        )
    return out


def _format_for_summary(messages: list[dict[str, Any]], max_chars: int = 12000) -> str:
    parts: list[str] = []
    total = 0
    for m in messages:
        role = str(m.get("role", "")).upper()
        content = str(m.get("content") or "")[:600]
        if not content and m.get("tool_calls"):
            content = f"[tool_calls: {len(m['tool_calls'])}]"
        line = f"[{role}]: {content}"
        if total + len(line) > max_chars:
            break
        parts.append(line)
        total += len(line)
    return "\n\n".join(parts)


def _summarize_middle(
    middle: list[dict[str, Any]], previous_summary: str = "",
) -> tuple[str, bool]:
    transcript = _format_for_summary(middle)
    if len(transcript) < 100:
        return previous_summary, False

    from butler.core.remote_compact import try_remote_summarize

    remote_summary = safe_best_effort(
        lambda: try_remote_summarize(middle, previous_summary),
        label="context_compressor.remote_summarize",
        default=None,
    )
    if remote_summary and str(remote_summary).strip():
        return str(remote_summary).strip(), True

    from butler.core.compaction_prompt import build_compaction_user_prompt

    prompt = build_compaction_user_prompt(
        transcript=transcript,
        previous_summary=previous_summary,
    )
    from butler.core.context_compress_support import auxiliary_summarize_middle

    text = auxiliary_summarize_middle(prompt)
    if text is None:
        logger.warning(
            "Summary LLM failed — aborting compression to preserve context",
        )
        return "", False
    return text, False


def compress_messages(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 128000,
    threshold_ratio: float = 0.5,
    previous_summary: str = "",
    min_messages_to_compress: int = _MIN_MESSAGES_TO_COMPRESS,
    head_count: int = 3,
    max_tail_messages: int = 12,
    min_tail_messages: int = 4,
    overflow_replay: bool = False,
    max_output_tokens: int | None = None,
    initial_injection: Any = None,
    diagnostics: dict[str, Any] | None = None,
    protected_keywords: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str, bool]:
    """Compress messages if over threshold. Returns (messages, summary, did_compress).

    Args:
        protected_keywords: List of keywords that, if found in middle messages,
            will protect those messages from summarization and include them in the tail.
    """
    from butler.core.context_compress_pipeline import run_compress_messages

    if protected_keywords is None:
        protected_keywords = _extract_keywords_from_latest_user(messages)

    if isinstance(diagnostics, dict) and protected_keywords:
        diagnostics["semantic_protection_keywords"] = len(protected_keywords)

    return cast(
        tuple[list[dict[str, Any]], str, bool],
        run_compress_messages(
            messages,
            max_tokens=max_tokens,
            threshold_ratio=threshold_ratio,
            previous_summary=previous_summary,
            min_messages_to_compress=min_messages_to_compress,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
            overflow_replay=overflow_replay,
            max_output_tokens=max_output_tokens,
            initial_injection=initial_injection,
            diagnostics=diagnostics,
            protected_keywords=protected_keywords,
        ),
    )


def _extract_keywords_from_latest_user(messages: list[dict[str, Any]]) -> list[str]:
    """Extract keywords from the latest user message for semantic protection."""
    import re

    for m in reversed(messages):
        if m.get("role") == "user":
            content = str(m.get("content") or "")
            words = re.findall(r"[\w\u4e00-\u9fff]{3,}", content)
            return words[:10]
    return []
