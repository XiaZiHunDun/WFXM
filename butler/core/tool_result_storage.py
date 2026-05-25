"""Persist oversized tool results to disk (Claude Code toolResultStorage subset)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

PERSISTED_OUTPUT_TAG = "<persisted-output>"
PERSISTED_OUTPUT_CLOSING_TAG = "</persisted-output>"
TOOL_RESULTS_SUBDIR = "tool-results"
_SESSIONS_SUBDIR = "sessions"

_DEFAULT_SPILL_MIN_CHARS = 8192
_DEFAULT_PREVIEW_CHARS = 2000
_SAFE_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9._+-]+")


def tool_result_spill_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_RESULT_SPILL", default=True)


def spill_threshold_chars() -> int:
    raw = os.getenv("BUTLER_TOOL_RESULT_SPILL_MIN_CHARS", "").strip()
    if not raw:
        return _DEFAULT_SPILL_MIN_CHARS
    try:
        return max(256, int(raw))
    except ValueError:
        return _DEFAULT_SPILL_MIN_CHARS


def spill_preview_chars() -> int:
    try:
        return max(200, int(os.getenv("BUTLER_TOOL_RESULT_SPILL_PREVIEW_CHARS", "") or _DEFAULT_PREVIEW_CHARS))
    except ValueError:
        return _DEFAULT_PREVIEW_CHARS


def is_persisted_tool_result(content: str) -> bool:
    return PERSISTED_OUTPUT_TAG in (content or "")


@dataclass(frozen=True)
class PersistedToolResult:
    filepath: Path
    original_size: int
    preview: str
    has_more: bool


def _safe_path_segment(value: str, *, fallback: str = "unknown") -> str:
    raw = str(value or "").strip() or fallback
    cleaned = _SAFE_SEGMENT_RE.sub("_", raw)
    return cleaned[:120] or fallback


def tool_results_dir(session_key: str) -> Path:
    """``~/.butler/sessions/<session>/tool-results/``."""
    sk = _safe_path_segment(session_key, fallback="_global")
    return get_butler_home() / _SESSIONS_SUBDIR / sk / TOOL_RESULTS_SUBDIR


def tool_result_path(session_key: str, tool_use_id: str) -> Path:
    tid = _safe_path_segment(tool_use_id, fallback="tool")
    return tool_results_dir(session_key) / f"{tid}.txt"


def generate_preview(content: str, max_chars: int) -> tuple[str, bool]:
    if len(content) <= max_chars:
        return content, False
    truncated = content[:max_chars]
    last_nl = truncated.rfind("\n")
    cut = last_nl if last_nl > max_chars // 2 else max_chars
    return content[:cut], True


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
    text = str(result or "")
    if len(text) <= spill_threshold_chars():
        return result
    if is_persisted_tool_result(text):
        return result

    tid = str(tool_use_id or "").strip() or f"tool_{tool_name or 'unknown'}"
    sk = str(session_key or "").strip()
    if not sk:
        from butler.execution_context import get_audit_session_key

        sk = get_audit_session_key(fallback="_global")

    persisted = persist_tool_result_text(text, tool_use_id=tid, session_key=sk)
    if persisted is None:
        return result
    return build_spill_message(persisted)


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
