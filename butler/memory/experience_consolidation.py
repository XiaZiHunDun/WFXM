"""Experience write-path digestion: vector near-neighbor + trusted-model merge."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, cast

from butler.env_parse import env_truthy, float_env

from butler.config import get_butler_home
from butler.memory.semantic_index import (
    index_experience_row,
    SOURCE_EXPERIENCE,
)
from butler.memory.experience_consolidation_ops import (
    inc_digestion_metric_safe,
    fusion_complete_loud,
)

logger = logging.getLogger(__name__)

_EXPERIENCE_MERGE_PROMPT = """Merge two experience bullets into ONE concise record for a personal assistant.

Rules:
- Remove duplication; keep distinct facts
- Preserve pointers verbatim: skill:, tool:, mcp:
- Max ~600 chars for content
- tags: union of both tag lists (comma-separated), deduplicated

## Existing
{existing}

## New
{new}

Output ONLY valid JSON:
{{"content": "...", "tags": "comma,separated"}}
"""


def experience_merge_enabled() -> bool:
    return bool(env_truthy("BUTLER_EXPERIENCE_MERGE", default=True))


def experience_merge_auto_threshold() -> float:
    try:
        return float(float_env("BUTLER_EXPERIENCE_MERGE_AUTO", 0.92, min=0.5, max=0.99))
    except ValueError:
        return 0.92


def experience_merge_review_threshold() -> float:
    try:
        return float(float_env("BUTLER_EXPERIENCE_MERGE_REVIEW", 0.78, min=0.4, max=0.99))
    except ValueError:
        return 0.78


def _pending_path() -> Path:

    d = cast(Path, get_butler_home()) / "metrics"
    d.mkdir(parents=True, exist_ok=True)
    return d / "experience_merge_pending.json"


def load_merge_pending() -> dict[str, dict[str, Any]]:
    path = _pending_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_merge_pending(entries: dict[str, dict[str, Any]]) -> None:
    path = _pending_path()
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def dismiss_merge_pending(key: str) -> dict[str, Any]:
    """Remove one pending merge entry. Returns ``{ok, key, ...}``."""
    pending = load_merge_pending()
    if key not in pending:
        return {"ok": False, "error": f"unknown key: {key}"}
    entry = pending.pop(key)
    save_merge_pending(pending)
    return {"ok": True, "key": key, "dismissed": entry}


def apply_merge_pending(
    key: str,
    *,
    butler_home: Path | None = None,
) -> dict[str, Any]:
    """Apply a queued merge to the existing experience row."""
    pending = load_merge_pending()
    entry = pending.get(key)
    if not entry:
        return {"ok": False, "error": f"unknown key: {key}"}

    row_id = int(entry.get("existing_id") or 0)
    if row_id <= 0:
        return {"ok": False, "error": "invalid existing_id in pending entry"}

    proposed_raw = entry.get("proposed")
    proposed: dict[str, Any] = proposed_raw if isinstance(proposed_raw, dict) else {}
    content = str(proposed.get("content") or "").strip()
    tags = proposed.get("tags")
    if not content:
        merged = fusion_merge_experience_text(
            str(entry.get("existing_content") or ""),
            str(entry.get("new_content") or ""),
        )
        content = str(merged.get("content") or "").strip()
        tags = merged.get("tags") or tags
        if not content or merged.get("fallback_used"):
            return {
                "ok": False,
                "error": "fusion merge failed; fix proposed content or retry later",
                "fallback_used": bool(merged.get("fallback_used")),
            }


    home = butler_home or get_butler_home()
    from butler.memory.butler_memory import ButlerMemory

    bm = ButlerMemory(home)
    try:
        if not bm.experience.update_content(row_id, content, tags=tags):
            return {"ok": False, "error": f"update_content failed for id={row_id}"}

        sem = bm.semantic
        if sem is not None:

            index_experience_row(
                sem,
                row_id,
                project=str(entry.get("project") or ""),
                category=str(entry.get("category") or ""),
                content=content,
            )

        pending.pop(key, None)
        save_merge_pending(pending)

        inc_digestion_metric_safe("digestion_experience_merged")
        return {
            "ok": True,
            "key": key,
            "row_id": row_id,
            "content_preview": content[:200],
            "similarity": entry.get("similarity"),
        }
    finally:
        bm.close()


def format_merge_pending_report(entries: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Human-readable lines for CLI / diagnostics."""
    pending = entries if entries is not None else load_merge_pending()
    if not pending:
        return ["经验合并待审队列为空。"]

    lines = [f"经验合并待审：{len(pending)} 条"]
    for key, entry in sorted(pending.items(), key=lambda kv: float(kv[1].get("ts") or 0)):
        sim = entry.get("similarity")
        row_id = entry.get("existing_id")
        proj = entry.get("project") or "-"
        cat = entry.get("category") or "-"
        ex = str(entry.get("existing_content") or "")[:80].replace("\n", " ")
        nw = str(entry.get("new_content") or "")[:80].replace("\n", " ")
        lines.append(
            f"  [{key}] id={row_id} sim={sim} project={proj} category={cat}\n"
            f"    existing: {ex}\n"
            f"    new:      {nw}"
        )
    lines.append("应用: butler memory merge-pending --apply <key>")
    lines.append("驳回: butler memory merge-pending --dismiss <key>")
    return lines


def queue_merge_pending(
    *,
    existing_id: int,
    existing_content: str,
    new_content: str,
    project: str,
    category: str,
    similarity: float,
    proposed: dict[str, Any] | None = None,
) -> str:
    pending = load_merge_pending()
    key = f"exp_merge_{existing_id}_{int(time.time())}"
    pending[key] = {
        "existing_id": existing_id,
        "existing_content": existing_content[:2000],
        "new_content": new_content[:2000],
        "project": project,
        "category": category,
        "similarity": round(similarity, 4),
        "proposed": proposed or {},
        "ts": time.time(),
    }
    save_merge_pending(pending)
    return key


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    for pattern in (r"\{[^{}]*\}", r"\{.*\}"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return cast(dict[str, Any], json.loads(m.group()))
            except json.JSONDecodeError:
                continue
    return None


def fusion_merge_experience_text(existing: str, new: str) -> dict[str, Any]:
    """Trusted-model merge; sets ``fallback_used`` when LLM path fails."""
    prompt = _EXPERIENCE_MERGE_PROMPT.format(existing=existing.strip(), new=new.strip())

    raw, err = fusion_complete_loud(prompt)
    if err is not None or raw is None:
        return {"content": existing.strip(), "tags": "", "fallback_used": True}

    data = _extract_json_object(raw)
    if not data or not str(data.get("content") or "").strip():
        return {"content": existing.strip(), "tags": "", "fallback_used": True}

    tags = data.get("tags", "")
    if isinstance(tags, list):
        tags = ",".join(str(t).strip() for t in tags if str(t).strip())
    return {
        "content": str(data.get("content", "")).strip()[:4000],
        "tags": str(tags or "").strip()[:500],
        "fallback_used": False,
    }


def find_similar_experience(
    butler_memory: Any,
    content: str,
    *,
    project: str | None = None,
    category: str = "",
) -> tuple[dict[str, Any] | None, float]:
    """Return (best hit with id, cosine similarity) for non-conversation experiences."""
    if (category or "") == "conversation":
        return None, 0.0
    text = (content or "").strip()
    if len(text) < 16:
        return None, 0.0

    semantic = getattr(butler_memory, "semantic", None)
    if semantic is None:
        return None, 0.0


    hits = semantic.search(text, project=project, limit=8)
    best: dict[str, Any] | None = None
    best_sim = 0.0
    for hit in hits:
        if str(hit.get("source") or "") != SOURCE_EXPERIENCE:
            continue
        if str(hit.get("category") or "") == "conversation":
            continue
        sim = float(hit.get("score") or 0.0)
        if sim > best_sim:
            best_sim = sim
            row_id = int(hit.get("source_id") or 0)
            best = {
                "id": row_id,
                "content": str(hit.get("content") or ""),
                "project": str(hit.get("project") or ""),
                "category": str(hit.get("category") or ""),
                "score": sim,
            }
    return best, best_sim


def digest_experience_add(
    butler_memory: Any,
    project: str,
    category: str,
    content: str,
    tags: str | list[str] | None = None,
) -> int:
    """Add or merge experience row. Returns row id, 0 on reject, -1 on queued pending."""
    if not experience_merge_enabled():
        return int(
            butler_memory._append_experience_row(
                project, category, content, tags=tags,
            )
        )

    best, sim = find_similar_experience(
        butler_memory,
        content,
        project=project or None,
        category=category or "",
    )
    auto_at = experience_merge_auto_threshold()
    review_at = experience_merge_review_threshold()

    if best and sim >= review_at and best.get("id"):
        merged = fusion_merge_experience_text(str(best.get("content") or ""), content)
        row_id = int(best["id"])

        if sim >= auto_at and not merged.get("fallback_used"):
            tag_merge = merged.get("tags") or ""
            if tags and not tag_merge:
                if isinstance(tags, list):
                    tag_merge = ",".join(tags)
                else:
                    tag_merge = str(tags)
            if butler_memory.experience.update_content(
                row_id,
                str(merged.get("content") or ""),
                tags=tag_merge or None,
            ):

                index_experience_row(
                    butler_memory.semantic,
                    row_id,
                    project=project or "",
                    category=category or "",
                    content=str(merged.get("content") or ""),
                )

                inc_digestion_metric_safe("digestion_experience_merged")
                return row_id

        queue_merge_pending(
            existing_id=row_id,
            existing_content=str(best.get("content") or ""),
            new_content=content,
            project=project or "",
            category=category or "",
            similarity=sim,
            proposed=merged,
        )

        inc_digestion_metric_safe("digestion_experience_merge_pending")
        return 0

    return int(butler_memory._append_experience_row(project, category, content, tags=tags))


__all__ = [
    "apply_merge_pending",
    "digest_experience_add",
    "dismiss_merge_pending",
    "experience_merge_auto_threshold",
    "experience_merge_enabled",
    "experience_merge_review_threshold",
    "find_similar_experience",
    "format_merge_pending_report",
    "fusion_merge_experience_text",
    "load_merge_pending",
    "queue_merge_pending",
]
