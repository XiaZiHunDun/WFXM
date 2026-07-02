"""Search L3/L4 coding_experiences.json via ``butler_recall`` (P3-H phase 1)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize_query(query: str) -> set[str]:
    raw = {t.lower() for t in _TOKEN_RE.findall(str(query or ""))}
    return {t for t in raw if len(t) >= 2}


def _experience_libraries(
    butler_home: Path,
    *,
    project_workspace: Path | None,
) -> list[Any]:
    from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary
    from butler.memory.memory_scope import (
        project_coding_experiences_path,
        tenant_coding_experiences_path,
    )

    tlib = TheoremLibrary()
    libs: list[Any] = []
    l4_path = tenant_coding_experiences_path(butler_home)
    if l4_path.is_file():
        libs.append(ExperienceLibrary.load_from_file(str(l4_path), theorem_lib=tlib))
    if project_workspace is not None:
        l3_path = project_coding_experiences_path(project_workspace)
        if l3_path.is_file():
            libs.append(ExperienceLibrary.load_from_file(str(l3_path), theorem_lib=tlib))
    return libs


def search_coding_experiences(
    query: str,
    *,
    limit: int = 8,
    project_id: str = "",
    project_workspace: Path | None = None,
    butler_home: Path | None = None,
    stack_tags: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Keyword search over tenant L4 + optional project L3 coding experience libraries."""
    q = str(query or "").strip()
    keywords = _tokenize_query(q)
    if not keywords:
        return {"ok": False, "error": "query is required (≥2 char tokens)"}

    from butler.config import get_butler_home
    from butler.memory.recall_ops import stack_tags_for_project_safe

    home = Path(butler_home or get_butler_home()).expanduser().resolve()
    lim = max(1, min(20, int(limit or 8)))
    pid = (project_id or "").strip()
    tags = stack_tags
    if tags is None and pid:
        from butler.memory.recall_ops import stack_tags_for_project_safe

        tags = stack_tags_for_project_safe(pid)

    libs = _experience_libraries(home, project_workspace=project_workspace)
    if not libs:
        return {
            "ok": True,
            "scope": "coding",
            "query": q,
            "results": [],
            "hint": "no coding_experiences.json (L4 tenant or L3 project)",
        }

    seen: set[str] = set()
    ranked: list[tuple[int, Any]] = []
    for lib in libs:
        for exp in lib.search(
            keywords,
            set(),
            strict_coverage=False,
            project_id=pid,
            stack_tags=tags,
        ):
            if exp.id in seen:
                continue
            seen.add(exp.id)
            score = lib._keyword_match_score(exp, keywords)
            ranked.append((score, exp))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    results: list[dict[str, Any]] = []
    for score, exp in ranked[:lim]:
        results.append(
            {
                "id": exp.id,
                "title": exp.title,
                "pattern": (exp.pattern or "")[:600],
                "context": (exp.context or "")[:240],
                "score": score,
                "scope_level": getattr(exp.scope, "level", ""),
                "project_id": getattr(exp.scope, "project_id", ""),
                "domain": list(exp.domain or []),
            }
        )

    return {
        "ok": True,
        "scope": "coding",
        "query": q,
        "project": pid or None,
        "results": results,
    }


def search_coding_experiences_json(**kwargs: Any) -> str:
    return json.dumps(search_coding_experiences(**kwargs), ensure_ascii=False)


__all__ = ["search_coding_experiences", "search_coding_experiences_json"]
