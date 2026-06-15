"""Pre-compression structured fact extraction.

Extracts key decisions, conclusions, and task state from conversation
messages before compression, so they survive lossy summarization.
Facts are stored per-session and re-injected as post-compact anchors.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_FACTS_PER_SESSION = 50
_MAX_FACT_VALUE_LEN = 300

from butler.tools.pim_schema import ALL_PIM_TOOLS as _PIM_TOOL_NAMES


def fact_extraction_enabled() -> bool:
    return os.getenv("BUTLER_FACT_EXTRACTION", "1").strip() in ("1", "true")


def _facts_dir() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "session_facts"


def _facts_path(session_key: str) -> Path:
    safe = re.sub(r"[^\w.-]", "_", session_key)[:80]
    return _facts_dir() / f"{safe}.json"


def load_facts(session_key: str) -> list[dict[str, Any]]:
    path = _facts_path(session_key)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_facts(session_key: str, facts: list[dict[str, Any]]) -> None:
    trimmed = facts[-_MAX_FACTS_PER_SESSION:]
    path = _facts_path(session_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trimmed, ensure_ascii=False, indent=1), encoding="utf-8")


def _extract_facts_from_messages(messages: list[dict]) -> list[dict[str, Any]]:
    """Heuristic extraction of structured facts from message content.

    Looks for:
    - Explicit decisions / conclusions in assistant messages
    - File modifications (patch/write_file tool calls)
    - Task completions / status changes
    - User preferences / corrections
    """
    from butler.core.tool_prune_policy import build_tool_name_index

    facts: list[dict[str, Any]] = []
    now = time.time()
    id_to_name = build_tool_name_index(messages)

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not isinstance(content, str) or not content.strip():
            continue

        if role == "assistant":
            _extract_assistant_facts(content, facts, now)
        elif role == "user":
            _extract_user_facts(content, facts, now)
        elif role == "tool":
            tid = str(msg.get("tool_call_id") or "").strip()
            tool_name = id_to_name.get(tid, "").strip().lower()
            if tool_name in _PIM_TOOL_NAMES:
                continue
            _extract_tool_facts(msg, facts, now)

    return facts


_DECISION_PATTERNS = [
    re.compile(r"(?:决定|结论|确认|方案)[：:]\s*(.{10,200})", re.DOTALL),
    re.compile(r"(?:最终|选择了?|采用|使用)\s*(.{10,100}?)(?:方案|方式|策略|架构)", re.DOTALL),
]

_COMPLETION_PATTERNS = [
    re.compile(r"(?:已完成|完成了|已实现|已修复|已更新)\s*(.{5,150})", re.DOTALL),
]


def _extract_assistant_facts(content: str, facts: list, now: float) -> None:
    for pattern in _DECISION_PATTERNS:
        for m in pattern.finditer(content):
            val = m.group(1).strip()[:_MAX_FACT_VALUE_LEN]
            if val:
                facts.append({
                    "type": "decision",
                    "value": val,
                    "ts": now,
                })

    for pattern in _COMPLETION_PATTERNS:
        for m in pattern.finditer(content):
            val = m.group(1).strip()[:_MAX_FACT_VALUE_LEN]
            if val:
                facts.append({
                    "type": "completion",
                    "value": val,
                    "ts": now,
                })


_PREFERENCE_PATTERNS = [
    re.compile(r"(?:不要|别|请勿|禁止)\s*(.{5,100})", re.DOTALL),
    re.compile(r"(?:我(?:想|要|希望|需要|倾向))\s*(.{5,100})", re.DOTALL),
]


def _extract_user_facts(content: str, facts: list, now: float) -> None:
    for pattern in _PREFERENCE_PATTERNS:
        for m in pattern.finditer(content):
            val = m.group(1).strip()[:_MAX_FACT_VALUE_LEN]
            if val and len(val) > 5:
                facts.append({
                    "type": "user_preference",
                    "value": val,
                    "ts": now,
                })


def _extract_tool_facts(msg: dict, facts: list, now: float) -> None:
    """Extract facts from tool results (file modifications, etc.)."""
    content = msg.get("content", "")
    if not isinstance(content, str):
        return
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(data, dict):
        return

    if data.get("ok") and data.get("path"):
        action = "modified" if data.get("action") == "patch" else "wrote"
        facts.append({
            "type": "file_change",
            "value": f"{action}: {data['path']}",
            "ts": now,
        })


def extract_pre_compact_facts(
    session_key: str,
    middle_messages: list[dict],
) -> list[dict[str, Any]]:
    """Extract facts from middle messages about to be compressed.

    Called from context_compressor before summarization.
    Returns extracted facts (also persisted to disk).
    """
    if not fact_extraction_enabled():
        return []

    new_facts = _extract_facts_from_messages(middle_messages)
    if not new_facts:
        return []

    existing = load_facts(session_key)
    existing_values = {f.get("value") for f in existing}
    deduped = [f for f in new_facts if f.get("value") not in existing_values]

    pre_count = len(existing)
    post_count = pre_count
    if deduped:
        merged = existing + deduped
        save_facts(session_key, merged)
        post_count = len(merged)
        logger.debug(
            "Extracted %d new facts (total %d) for session %s",
            len(deduped),
            len(merged),
            session_key[:20],
        )

    try:
        from butler.memory.memory_metrics import get_collector

        get_collector().on_fact_extraction(pre_count=pre_count, post_count=post_count)
    except Exception:
        pass

    return deduped


def count_facts_for_anchor(session_key: str) -> tuple[int, int]:
    """Return (store_count, anchor_count) for S_f telemetry.

    ``anchor_count`` matches ``format_facts_for_anchor`` (recent 20 cap).
    """
    facts = load_facts(session_key)
    store = len(facts)
    if store == 0:
        return 0, 0
    return store, min(store, 20)


def record_fact_anchor_metrics(
    session_key: str,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """Record per-compaction fact survival for /诊断 and L2 metrics."""
    store, anchor = count_facts_for_anchor(session_key)
    if diagnostics is not None:
        diagnostics["facts_store_count"] = store
        diagnostics["facts_anchor_count"] = anchor
        if store > 0:
            diagnostics["fact_survival_rate_turn"] = round(anchor / store, 4)
    if store > 0:
        try:
            from butler.memory.memory_metrics import get_collector

            get_collector().on_fact_anchor_survival(store_count=store, anchor_count=anchor)
        except Exception:
            pass
    return store, anchor


def format_facts_for_anchor(session_key: str, *, max_chars: int = 2000) -> str:
    """Format stored facts as a post-compact anchor block."""
    facts = load_facts(session_key)
    if not facts:
        return ""

    recent = facts[-20:]

    by_type: dict[str, list[str]] = {}
    for f in recent:
        ftype = f.get("type", "other")
        by_type.setdefault(ftype, []).append(f.get("value", ""))

    lines = ["## 会话关键事实"]
    type_labels = {
        "decision": "决策",
        "completion": "已完成",
        "user_preference": "用户偏好",
        "file_change": "文件变更",
    }
    for ftype, values in by_type.items():
        label = type_labels.get(ftype, ftype)
        lines.append(f"\n### {label}")
        for v in values[-5:]:
            lines.append(f"- {v}")

    result = "\n".join(lines)
    return result[:max_chars]
