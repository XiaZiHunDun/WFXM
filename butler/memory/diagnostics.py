"""Memory layer stats for /诊断 and ops."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from butler.session_lifecycle import CONVERSATION_CATEGORY


def _experience_category_counts(db_path: Any) -> dict[str, int]:
    path = getattr(db_path, "path", db_path)
    if not path or not str(path):
        return {}
    try:
        conn = sqlite3.connect(str(path))
        rows = conn.execute(
            "SELECT category, COUNT(*) FROM experiences GROUP BY category"
        ).fetchall()
        conn.close()
        return {str(cat or ""): int(n) for cat, n in rows}
    except Exception:
        return {}


def _resolve_project_memory(orchestrator: Any, session_key: str = ""):
    """Project MEMORY for diagnostics; prefers session_key over global _project_memory."""
    pm = getattr(orchestrator, "_project_memory", None)
    proj = None
    pman = getattr(orchestrator, "project_manager", None)
    if pman is not None:
        try:
            proj = pman.get_current(session_key=session_key or "")
        except Exception:
            proj = None
    if proj is not None:
        from butler.memory.project_memory import ProjectMemory

        ws = getattr(proj, "workspace", None)
        if ws is not None:
            root = Path(ws).expanduser()
            if root.is_dir():
                name = str(getattr(proj, "name", "") or root.name)
                return ProjectMemory(root), name
    if pm is not None:
        from butler.memory.semantic_project import resolve_project_display_name

        return pm, resolve_project_display_name(pm)
    return None, ""


def collect_memory_layer_stats(
    orchestrator: Any,
    *,
    session_key: str = "",
) -> dict[str, Any]:
    """Snapshot counts for owner profile, experience.db, and project MEMORY.md."""
    stats: dict[str, Any] = {
        "profile_entries": 0,
        "profile_chars": 0,
        "experience_by_category": {},
        "experience_long_term": 0,
        "conversation_rows": 0,
        "semantic_enabled": False,
        "vector_rows": 0,
        "vector_model": "",
        "project_name": "",
        "project_pending": 0,
        "project_bullets": 0,
        "project_chars": 0,
    }

    bm = getattr(orchestrator, "butler_memory", None)
    if bm is not None:
        prof = getattr(bm, "profile", None)
        if prof is not None:
            entries = getattr(prof, "_entries", None)
            if isinstance(entries, list):
                stats["profile_entries"] = len(entries)
                stats["profile_chars"] = sum(len(e) for e in entries)
            else:
                text = prof.read() if hasattr(prof, "read") else ""
                stats["profile_chars"] = len(text or "")

        sem = getattr(bm, "semantic", None)
        if sem is not None:
            stats["semantic_enabled"] = True
            try:
                stats["vector_rows"] = sem.count_rows()
                stats["vector_model"] = getattr(sem, "model_id", "") or ""
            except Exception:
                pass

        exp = getattr(bm, "experience", None)
        if exp is not None:
            by_cat = _experience_category_counts(getattr(exp, "db_path", None))
            stats["experience_by_category"] = by_cat
            stats["conversation_rows"] = by_cat.get(CONVERSATION_CATEGORY, 0)
            stats["experience_long_term"] = sum(
                n for k, n in by_cat.items() if k != CONVERSATION_CATEGORY
            )

    pm, proj_name = _resolve_project_memory(orchestrator, session_key)
    if pm is not None:
        stats["project_name"] = proj_name
        md = getattr(pm, "markdown", None)
        if md is not None:
            try:
                stats["project_pending"] = len(md.list_pending())
            except Exception:
                stats["project_pending"] = 0
            try:
                sections = md.get_all_sections()
                bullets = 0
                chars = 0
                for name, body in sections.items():
                    if name == "Pending":
                        continue
                    for line in (body or "").splitlines():
                        if line.strip().startswith("- "):
                            bullets += 1
                            chars += len(line)
                stats["project_bullets"] = bullets
                stats["project_chars"] = chars
            except Exception:
                pass

    return stats


def format_memory_diagnostic_lines(stats: dict[str, Any]) -> list[str]:
    """Human-readable lines for gateway /诊断."""
    if not stats:
        return ["记忆分层: 无数据"]

    lines = [
        "记忆分层:",
        f"  Owner 画像: {stats.get('profile_entries', 0)} 条 / "
        f"{stats.get('profile_chars', 0)} 字",
        f"  Experience: 长期 {stats.get('experience_long_term', 0)} 条, "
        f"会话回声 {stats.get('conversation_rows', 0)} 条",
    ]
    proj = stats.get("project_name") or "（未选项目）"
    lines.append(
        f"  项目 MEMORY ({proj}): 正式条目 {stats.get('project_bullets', 0)} 条, "
        f"Pending {stats.get('project_pending', 0)} 条"
    )
    if stats.get("semantic_enabled"):
        lines.append(
            f"  向量索引: {stats.get('vector_rows', 0)} 条 "
            f"(model={stats.get('vector_model') or '?'})"
        )
    else:
        lines.append("  向量索引: 关 (BUTLER_SEMANTIC_MEMORY=0)")
    injected = stats.get("last_prefetch_chars")
    if injected is not None:
        lines.append(f"  上轮预取注入: {injected} 字")
    return lines
