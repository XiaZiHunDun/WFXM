"""Persist oversized tool results to disk (Claude Code toolResultStorage subset)."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

PERSISTED_OUTPUT_TAG = "<persisted-output>"
PERSISTED_OUTPUT_CLOSING_TAG = "</persisted-output>"
INJECT_ONCE_REF_TAG = "<persisted-output-ref>"
INJECT_ONCE_REF_CLOSING_TAG = "</persisted-output-ref>"
TOOL_RESULTS_SUBDIR = "tool-results"
_SESSIONS_SUBDIR = "sessions"
BUDGET_TRUNCATED_TAG = "<tool-result-truncated>"
EMPTY_TOOL_RESULT_TEMPLATE = "({tool_name} completed with no output)"

_DEFAULT_SPILL_MIN_CHARS = 8192
_DEFAULT_PREVIEW_CHARS = 2000
_DEFAULT_MESSAGE_MAX_CHARS = 200_000
_NO_SPILL_TOOLS = frozenset({"read_file", "skills_list", "skill_view"})

_SAFE_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9._+-]+")
_LOCK = threading.RLock()
_REPLACEMENT_BY_SESSION: dict[str, "ContentReplacementState"] = {}
_INJECT_ONCE_BY_SESSION: dict[str, "InjectOnceState"] = {}
_PER_TOOL_THRESHOLDS_CACHE: dict[str, int] | None = None
_FILEPATH_IN_SPILL_RE = re.compile(r"完整结果已保存至[：:]\s*(\S+)")
_SIZE_IN_SPILL_RE = re.compile(r"输出过大[（(](\d+)\s*字符")


def tool_result_spill_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_RESULT_SPILL", default=True)


def tool_result_inject_once_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_RESULT_INJECT_ONCE", default=True)


def message_tool_budget_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_RESULT_MESSAGE_BUDGET", default=True)


def spill_threshold_chars(tool_name: str = "") -> int:
    """Per-tool spill threshold; 0 means never spill (self-bounded tools)."""
    name = str(tool_name or "").strip()
    if name in _NO_SPILL_TOOLS:
        return 0
    per_tool = _load_per_tool_thresholds()
    if name and name in per_tool:
        val = per_tool[name]
        return 0 if val <= 0 else max(256, val)
    raw = os.getenv("BUTLER_TOOL_RESULT_SPILL_MIN_CHARS", "").strip()
    if not raw:
        return _DEFAULT_SPILL_MIN_CHARS
    try:
        return max(256, int(raw))
    except ValueError:
        return _DEFAULT_SPILL_MIN_CHARS


def _load_per_tool_thresholds() -> dict[str, int]:
    global _PER_TOOL_THRESHOLDS_CACHE
    if _PER_TOOL_THRESHOLDS_CACHE is not None:
        return _PER_TOOL_THRESHOLDS_CACHE
    raw = os.getenv("BUTLER_TOOL_RESULT_THRESHOLDS", "").strip()
    out: dict[str, int] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    try:
                        out[str(k)] = int(v)
                    except (TypeError, ValueError):
                        continue
        except json.JSONDecodeError:
            logger.warning("Invalid BUTLER_TOOL_RESULT_THRESHOLDS JSON")
    _PER_TOOL_THRESHOLDS_CACHE = out
    return out


def message_tool_budget_max_chars() -> int:
    raw = os.getenv("BUTLER_TOOL_RESULT_MESSAGE_MAX_CHARS", "").strip()
    if not raw:
        return _DEFAULT_MESSAGE_MAX_CHARS
    try:
        return max(10_000, int(raw))
    except ValueError:
        return _DEFAULT_MESSAGE_MAX_CHARS


def spill_preview_chars() -> int:
    try:
        from butler.env_parse import int_env

        return int_env("BUTLER_TOOL_RESULT_SPILL_PREVIEW_CHARS", _DEFAULT_PREVIEW_CHARS, min=200)
    except ValueError:
        return _DEFAULT_PREVIEW_CHARS


def is_persisted_tool_result(content: str) -> bool:
    text = content or ""
    return PERSISTED_OUTPUT_TAG in text or INJECT_ONCE_REF_TAG in text


def is_inject_once_ref(content: str) -> bool:
    return INJECT_ONCE_REF_TAG in (content or "")


def is_budget_truncated_tool_result(content: str) -> bool:
    return BUDGET_TRUNCATED_TAG in (content or "")


def normalize_empty_tool_result(content: str, *, tool_name: str = "") -> str:
    """Avoid empty tool results confusing stop sequences (CC toolResultStorage)."""
    text = str(content or "")
    if text.strip():
        return content
    label = str(tool_name or "tool").strip() or "tool"
    return EMPTY_TOOL_RESULT_TEMPLATE.format(tool_name=label)


@dataclass
class PersistedToolResult:
    filepath: Path
    original_size: int
    preview: str
    has_more: bool


@dataclass
class ContentReplacementRecord:
    tool_use_id: str
    replacement: str
    original_chars: int


@dataclass
class ContentReplacementState:
    """Frozen per tool_use_id replacement decisions (CC cache-stable budget)."""

    seen_ids: set[str] = field(default_factory=set)
    replacements: dict[str, str] = field(default_factory=dict)

    def clone(self) -> ContentReplacementState:
        return ContentReplacementState(
            seen_ids=set(self.seen_ids),
            replacements=dict(self.replacements),
        )


@dataclass
class SpillInjectMeta:
    tool_use_id: str
    filepath: str
    original_size: int
    summary_line: str
    tool_name: str = ""


@dataclass
class InjectOnceState:
    """Track which spilled tool_use_ids already had a full inject this turn/session."""

    injected_ids: set[str] = field(default_factory=set)
    spill_meta: dict[str, SpillInjectMeta] = field(default_factory=dict)


def get_replacement_state(session_key: str = "") -> ContentReplacementState:
    sk = _safe_path_segment(session_key or "_global", fallback="_global")
    with _LOCK:
        if sk not in _REPLACEMENT_BY_SESSION:
            _REPLACEMENT_BY_SESSION[sk] = ContentReplacementState()
        return _REPLACEMENT_BY_SESSION[sk]


def reset_replacement_state(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _REPLACEMENT_BY_SESSION.clear()
            return
        sk = _safe_path_segment(session_key, fallback="_global")
        _REPLACEMENT_BY_SESSION.pop(sk, None)


def get_inject_once_state(session_key: str = "") -> InjectOnceState:
    sk = _safe_path_segment(session_key or "_global", fallback="_global")
    with _LOCK:
        if sk not in _INJECT_ONCE_BY_SESSION:
            _INJECT_ONCE_BY_SESSION[sk] = InjectOnceState()
        return _INJECT_ONCE_BY_SESSION[sk]


def reset_inject_once_state(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _INJECT_ONCE_BY_SESSION.clear()
            return
        sk = _safe_path_segment(session_key, fallback="_global")
        _INJECT_ONCE_BY_SESSION.pop(sk, None)


def _safe_path_segment(value: str, *, fallback: str = "unknown") -> str:
    raw = str(value or "").strip() or fallback
    cleaned = _SAFE_SEGMENT_RE.sub("_", raw)
    return cleaned[:120] or fallback


def tool_results_dir(session_key: str) -> Path:
    """``~/.butler/sessions/<session>/tool-results/``."""
    sk = _safe_path_segment(session_key, fallback="_global")
    return get_butler_home() / _SESSIONS_SUBDIR / sk / TOOL_RESULTS_SUBDIR


def is_readable_session_tool_result_path(
    path_str: str,
    *,
    session_key: str = "",
) -> bool:
    """Read-only spill files for the active session (outside project workspace)."""
    raw = str(path_str or "").strip()
    if not raw:
        return False
    from butler.execution_context import get_current_session_key
    from butler.core.tool_result_storage_ops import is_readable_session_tool_result_path_safe

    return is_readable_session_tool_result_path_safe(
        raw,
        session_key=session_key,
        allowed_dir_for_session=tool_results_dir,
        current_session_key=get_current_session_key,
    )


def tool_result_path(session_key: str, tool_use_id: str) -> Path:
    tid = _safe_path_segment(tool_use_id, fallback="tool")
    return tool_results_dir(session_key) / f"{tid}.txt"


def generate_preview(content: str, max_chars: int) -> tuple[str, bool]:
    from butler.core.text_truncate import truncate_text

    return truncate_text(content, max_chars, suffix="\n…(truncated)", prefer_newline=True)


def persist_tool_result_text(
    content: str,
    *,
    tool_use_id: str,
    session_key: str = "",
) -> PersistedToolResult | None:
    """Write content to session tool-results dir. Returns None on failure."""
    if not content:
        return None
    path = tool_result_path(session_key, tool_use_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as fh:
            fh.write(content)
        logger.info(
            "Spilled tool result tool_use_id=%s session=%s size=%d path=%s",
            tool_use_id,
            session_key or "_global",
            len(content),
            path,
        )
    except FileExistsError:
        if not path.is_file():
            return None
    except OSError as exc:
        logger.warning("Tool result spill failed path=%s: %s", path, exc)
        return None

    preview, has_more = generate_preview(content, spill_preview_chars())
    return PersistedToolResult(
        filepath=path.resolve(),
        original_size=len(content),
        preview=preview,
        has_more=has_more,
    )


def _first_summary_line(preview: str) -> str:
    for line in (preview or "").splitlines():
        text = line.strip()
        if text and text != "...":
            return text[:240]
    return ""


def register_spill_inject_meta(
    *,
    tool_use_id: str,
    session_key: str,
    persisted: PersistedToolResult,
    tool_name: str = "",
) -> None:
    tid = str(tool_use_id or "").strip()
    if not tid:
        return
    sk = str(session_key or "").strip() or "_global"
    state = get_inject_once_state(sk)
    state.spill_meta[tid] = SpillInjectMeta(
        tool_use_id=tid,
        filepath=str(persisted.filepath),
        original_size=int(persisted.original_size),
        summary_line=_first_summary_line(persisted.preview),
        tool_name=str(tool_name or "").strip(),
    )


def parse_spill_meta_from_content(content: str, *, tool_use_id: str = "") -> SpillInjectMeta | None:
    text = str(content or "")
    if PERSISTED_OUTPUT_TAG not in text:
        return None
    path_m = _FILEPATH_IN_SPILL_RE.search(text)
    size_m = _SIZE_IN_SPILL_RE.search(text)
    if not path_m:
        return None
    preview_block = ""
    if "预览" in text:
        parts = text.split("预览", 1)
        if len(parts) > 1:
            preview_block = parts[1].split(PERSISTED_OUTPUT_CLOSING_TAG, 1)[0]
    return SpillInjectMeta(
        tool_use_id=str(tool_use_id or "").strip(),
        filepath=path_m.group(1).strip(),
        original_size=int(size_m.group(1)) if size_m else len(text),
        summary_line=_first_summary_line(preview_block),
    )


def build_inject_once_compact_message(meta: SpillInjectMeta) -> str:
    summary = meta.summary_line or "(无摘要)"
    tool = f" [{meta.tool_name}]" if meta.tool_name else ""
    return "\n".join(
        [
            INJECT_ONCE_REF_TAG,
            f"inject_once{tool}：完整输出已在上一轮注入，此处仅保留指针。",
            f"路径：{meta.filepath}",
            f"大小：{meta.original_size} 字符",
            f"摘要：{summary}",
            INJECT_ONCE_REF_CLOSING_TAG,
        ]
    )


def build_spill_message(result: PersistedToolResult) -> str:
    preview_limit = spill_preview_chars()
    lines = [
        PERSISTED_OUTPUT_TAG,
        (
            f"输出过大（{result.original_size} 字符）。"
            f"完整结果已保存至：{result.filepath}"
        ),
        "",
        f"预览（前 {preview_limit} 字符）：",
        result.preview,
    ]
    if result.has_more:
        lines.append("...")
    lines.append(PERSISTED_OUTPUT_CLOSING_TAG)
    return "\n".join(lines)


def build_budget_truncation_message(
    *,
    tool_use_id: str,
    original_chars: int,
    kept_chars: int,
) -> str:
    return (
        f"{BUDGET_TRUNCATED_TAG}\n"
        f"工具结果因单轮上下文预算被截断（tool_use_id={tool_use_id}，"
        f"原 {original_chars} 字符，保留 {kept_chars} 字符）。"
        "完整内容可能已落盘或请缩小查询范围后重试。"
    )


def maybe_spill_tool_result(
    result: str,
    *,
    tool_name: str = "",
    tool_use_id: str = "",
    session_key: str = "",
) -> str:
    """Replace oversized tool result text with a persisted-output pointer."""
    if not tool_result_spill_enabled():
        return result
    text = normalize_empty_tool_result(str(result or ""), tool_name=tool_name)
    threshold = spill_threshold_chars(tool_name)
    if threshold <= 0 or len(text) <= threshold:
        return text
    if is_persisted_tool_result(text):
        return text

    tid = str(tool_use_id or "").strip() or f"tool_{tool_name or 'unknown'}"
    sk = str(session_key or "").strip()
    if not sk:
        from butler.execution_context import get_audit_session_key

        sk = get_audit_session_key(fallback="_global")

    persisted = persist_tool_result_text(text, tool_use_id=tid, session_key=sk)
    if persisted is None:
        return text
    if tool_result_inject_once_enabled():
        register_spill_inject_meta(
            tool_use_id=tid,
            session_key=sk,
            persisted=persisted,
            tool_name=tool_name,
        )
    return build_spill_message(persisted)


def apply_inject_once_policy(
    messages: list[dict],
    *,
    session_key: str = "",
) -> list[dict]:
    """
    First API round keeps full ``<persisted-output>``; later rounds compact to ref+summary.
    Mutates tool message dicts in ``messages`` in place.
    """
    if not tool_result_inject_once_enabled() or not tool_result_spill_enabled():
        return messages
    sk = str(session_key or "").strip()
    if not sk:
        from butler.execution_context import get_audit_session_key

        sk = get_audit_session_key(fallback="_global")
    state = get_inject_once_state(sk)
    name_index = _build_tool_name_index(messages)

    for msg in messages:
        if msg.get("role") != "tool":
            continue
        tid = str(msg.get("tool_call_id") or msg.get("id") or "").strip()
        if not tid:
            continue
        content = str(msg.get("content") or "")
        if is_inject_once_ref(content):
            continue
        if not is_persisted_tool_result(content) or PERSISTED_OUTPUT_TAG not in content:
            continue
        meta = state.spill_meta.get(tid)
        if meta is None:
            meta = parse_spill_meta_from_content(content, tool_use_id=tid)
            if meta is not None:
                meta.tool_name = name_index.get(tid, meta.tool_name)
                state.spill_meta[tid] = meta
        if meta is None:
            continue
        if tid in state.injected_ids:
            msg["content"] = build_inject_once_compact_message(meta)
            continue
        state.injected_ids.add(tid)
    return messages


def _build_tool_name_index(messages: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            if not tid:
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            out[tid] = str(fn.get("name") or "").strip()
    return out


def _tool_result_char_len(msg: dict) -> int:
    content = msg.get("content")
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                total += len(str(block.get("text") or block.get("content") or ""))
        return total
    return len(str(content or ""))


def _iter_tool_messages(messages: list[dict]) -> list[tuple[int, dict, str]]:
    out: list[tuple[int, dict, str]] = []
    for idx, msg in enumerate(messages):
        if msg.get("role") != "tool":
            continue
        tid = str(msg.get("tool_call_id") or msg.get("id") or f"idx_{idx}")
        out.append((idx, msg, tid))
    return out


def enforce_message_tool_budget(
    messages: list[dict],
    *,
    session_key: str = "",
    max_chars: int | None = None,
) -> list[dict]:
    """Cap aggregate tool_result chars per API round (CC enforceToolResultBudget)."""
    if not message_tool_budget_enabled():
        return messages
    limit = max_chars if max_chars is not None else message_tool_budget_max_chars()
    tool_rows = _iter_tool_messages(messages)
    if not tool_rows:
        return messages

    total = sum(_tool_result_char_len(msg) for _, msg, _ in tool_rows)
    if total <= limit:
        return messages

    sk = str(session_key or "").strip()
    if not sk:
        from butler.execution_context import get_audit_session_key

        sk = get_audit_session_key(fallback="_global")
    state = get_replacement_state(sk)

    out = list(messages)
    remaining = limit
    for idx, msg, tid in tool_rows:
        if tid in state.replacements:
            out[idx] = {**msg, "content": state.replacements[tid]}
            remaining -= len(state.replacements[tid])
            continue

        content = str(msg.get("content") or "")
        state.seen_ids.add(tid)
        clen = len(content)
        if clen <= remaining:
            state.replacements[tid] = content
            remaining -= clen
            continue

        if remaining > 200 and is_persisted_tool_result(content):
            state.replacements[tid] = content
            remaining -= clen
            continue

        if remaining > 500 and tool_result_spill_enabled():
            spilled = maybe_spill_tool_result(
                content,
                tool_use_id=tid,
                session_key=sk,
            )
            if spilled != content and len(spilled) < clen:
                state.replacements[tid] = spilled
                out[idx] = {**msg, "content": spilled}
                remaining -= len(spilled)
                continue

        keep = max(0, remaining)
        truncated = content[:keep] if keep else ""
        replacement = build_budget_truncation_message(
            tool_use_id=tid,
            original_chars=clen,
            kept_chars=keep,
        )
        if truncated:
            replacement = truncated + "\n\n" + replacement
        state.replacements[tid] = replacement
        out[idx] = {**msg, "content": replacement}
        remaining = 0

    return out


def spill_stats_for_session(session_key: str) -> dict[str, Any]:
    """Best-effort count of spilled files for diagnostics."""
    root = tool_results_dir(session_key)
    if not root.is_dir():
        return {"spill_files": 0, "spill_dir": str(root)}
    files = list(root.glob("*.txt"))
    total_bytes = sum(p.stat().st_size for p in files if p.is_file())
    return {
        "spill_files": len(files),
        "spill_bytes": total_bytes,
        "spill_dir": str(root),
    }
