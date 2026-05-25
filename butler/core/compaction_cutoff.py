"""Safe message boundaries before compaction (LangChain SummarizationMiddleware subset)."""

from __future__ import annotations


def _prefix_tool_pairs_closed(messages: list[dict], boundary: int) -> bool:
    pending: set[str] = set()
    for msg in messages[:boundary]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                tid = str(tc.get("id") or "").strip()
                if tid:
                    pending.add(tid)
        elif role == "tool":
            tid = str(msg.get("tool_call_id") or "").strip()
            if tid:
                pending.discard(tid)
    return len(pending) == 0


def find_safe_tail_start(messages: list[dict], proposed_tail_start: int) -> int:
    """
    Return the earliest index ``>= proposed_tail_start`` safe for compaction tail.

    - No assistant ``tool_calls`` in the summarizable prefix lack tool rows in that prefix.
    - Tail does not begin between an assistant ``tool_calls`` block and its tool results.
    """
    n = len(messages)
    start = max(0, min(int(proposed_tail_start), n))
    while start < n and not _prefix_tool_pairs_closed(messages, start):
        start += 1
    while start < n:
        msg = messages[start] if isinstance(messages[start], dict) else {}
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            end = start + 1
            while end < n and isinstance(messages[end], dict) and messages[end].get("role") == "tool":
                end += 1
            if end > start + 1:
                return end
        return start
    return n


def apply_safe_tail_start(messages: list[dict], proposed_tail_start: int) -> int:
    """Alias used by turn compaction and legacy head/tail split."""
    return find_safe_tail_start(messages, proposed_tail_start)
