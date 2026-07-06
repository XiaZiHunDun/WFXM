"""Multi-project memory scope diagnostics (L3/L4 coding experiences)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from butler.memory.memory_scope import (
    project_coding_experiences_path,
    tenant_coding_experiences_path,
)


def _load_json_experiences(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _scope_dict_from_record(rec: dict[str, Any]) -> dict[str, Any]:
    scope = rec.get("scope") if isinstance(rec.get("scope"), dict) else {}
    if scope:
        return scope
    from butler.memory.memory_scope import infer_default_scope

    inferred = infer_default_scope(
        exp_id=str(rec.get("id") or ""),
        domain=rec.get("domain") if isinstance(rec.get("domain"), list) else None,
    )
    return cast(dict[str, Any], inferred.to_dict())


def _scope_summary_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_vis: dict[str, int] = {}
    by_project: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for rec in records:
        scope = _scope_dict_from_record(rec)
        vis = str(scope.get("visibility") or "global")
        by_vis[vis] = by_vis.get(vis, 0) + 1
        pid = str(scope.get("project_id") or "").strip()
        if pid:
            by_project[pid] = by_project.get(pid, 0) + 1
        src = str(scope.get("source") or "manual")
        by_source[src] = by_source.get(src, 0) + 1
    return {
        "total": len(records),
        "by_visibility": by_vis,
        "by_project_id": by_project,
        "by_source": by_source,
    }


def _lessons_for_project(
    lessons_path: Path,
    *,
    project_name: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    if not lessons_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in lessons_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if project_name and str(row.get("project") or "") != project_name:
            continue
        rows.append(row)
    return rows[-limit:]


def _resolve_workspace(project_name: str) -> Path | None:
    from butler.memory.scope_diagnostics_ops import resolve_project_workspace_safe

    return cast(Path | None, resolve_project_workspace_safe(project_name))


def collect_memory_scope_stats(
    *,
    butler_home: Path,
    project_name: str = "",
) -> dict[str, Any]:
    """Snapshot L3/L4 coding experience scope + recent production lessons."""
    home = Path(butler_home).expanduser().resolve()
    pname = str(project_name or "").strip()

    l4_path = tenant_coding_experiences_path(home)
    l4_records = _load_json_experiences(l4_path)
    l4_all = _scope_summary_from_records(l4_records)

    l4_visible = l4_all
    if pname:
        from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary
        from butler.memory.scope_diagnostics_ops import stack_tags_for_project_safe

        ws = _resolve_workspace(pname)
        stack_tags = stack_tags_for_project_safe(pname) if ws is not None else frozenset()

        xlib = ExperienceLibrary.load_from_file(str(l4_path), theorem_lib=TheoremLibrary())
        visible = 0
        by_vis: dict[str, int] = {}
        for exp in xlib._experiences.values():
            if not exp.scope.visible_to(project_id=pname, stack_tags=stack_tags):
                continue
            visible += 1
            by_vis[exp.scope.visibility] = by_vis.get(exp.scope.visibility, 0) + 1
        l4_visible = {
            "total": visible,
            "by_visibility": by_vis,
            "filter_project": pname,
        }

    l3_path: Path | None = None
    l3_summary: dict[str, Any] = {"total": 0, "by_visibility": {}, "by_source": {}}
    ws = _resolve_workspace(pname) if pname else None
    if ws is not None:
        l3_path = project_coding_experiences_path(ws)
        l3_summary = _scope_summary_from_records(_load_json_experiences(l3_path))

    lessons_path = home / "audit" / "b9_lessons.jsonl"
    recent_lessons = _lessons_for_project(lessons_path, project_name=pname, limit=5)
    prod_lessons = sum(
        1
        for row in _lessons_for_project(lessons_path, project_name=pname, limit=10_000)
        if str(row.get("kind") or "") == "production_failure"
    )

    projects_overview: list[dict[str, Any]] = []
    if not pname:
        from butler.memory.scope_diagnostics_ops import list_projects_l3_overview_safe

        projects_overview = list_projects_l3_overview_safe()

    return {
        "project": pname or None,
        "l4_tenant_path": str(l4_path),
        "l4_tenant": l4_all,
        "l4_visible_to_project": l4_visible if pname else None,
        "l3_project_path": str(l3_path) if l3_path else None,
        "l3_project": l3_summary,
        "b9_lessons_path": str(lessons_path),
        "production_failure_lessons": prod_lessons,
        "recent_lessons": recent_lessons,
        "projects_l3_overview": projects_overview,
    }


def format_memory_scope_diagnostic_lines(stats: dict[str, Any]) -> list[str]:
    """Human-readable lines for /诊断 and ``butler memory diagnose``."""
    if not stats:
        return []

    lines = ["编码经验作用域 (L3/L4):"]
    l4 = stats.get("l4_tenant") or {}
    lines.append(
        f"  L4 租户库: {l4.get('total', 0)} 条 "
        f"(global={l4.get('by_visibility', {}).get('global', 0)}, "
        f"private={l4.get('by_visibility', {}).get('private', 0)}, "
        f"stack={l4.get('by_visibility', {}).get('stack', 0)})"
    )

    proj = stats.get("project")
    if proj:
        l4v = stats.get("l4_visible_to_project") or {}
        lines.append(
            f"  L4→{proj} 可见: {l4v.get('total', 0)} 条"
        )
        l3 = stats.get("l3_project") or {}
        lines.append(
            f"  L3 项目库 ({proj}): {l3.get('total', 0)} 条 "
            f"(source={l3.get('by_source', {})})"
        )
        pf = int(stats.get("production_failure_lessons") or 0)
        if pf:
            lines.append(f"  生产失败 lesson: {pf} 条 (b9_lessons)")
        recent = stats.get("recent_lessons") or []
        if recent:
            last = recent[-1]
            lines.append(
                f"  最近 lesson: [{last.get('kind')}] "
                f"{str(last.get('classification') or '')} "
                f"task={str(last.get('task_id') or '')[:24]}"
            )
    else:
        overview = stats.get("projects_l3_overview") or []
        if overview:
            lines.append("  L3 项目库概览:")
            for row in overview[:8]:
                lines.append(
                    f"    · {row.get('project')}: {row.get('l3_total', 0)} 条"
                )
        else:
            lines.append("  L3 项目库: （尚无 per-project coding_experiences.json）")

    return lines


def run_memory_scope_diagnose(
    *,
    butler_home: Path,
    project: str = "",
    json_out: bool = False,
) -> dict[str, Any]:
    stats = collect_memory_scope_stats(
        butler_home=butler_home,
        project_name=project,
    )
    payload = {
        "ok": True,
        "project": project or None,
        "stats": stats,
        "lines": format_memory_scope_diagnostic_lines(stats),
    }
    if json_out:
        return payload
    return payload


def backfill_tenant_coding_scopes(
    *,
    butler_home: Path,
    dry_run: bool = True,
) -> dict[str, Any]:
    """P5: persist inferred MemoryScope onto legacy L4 tenant rows."""
    from butler.memory.memory_scope import MemoryScope, infer_default_scope

    l4_path = tenant_coding_experiences_path(butler_home)
    records = _load_json_experiences(l4_path)
    updated = 0
    for rec in records:
        if isinstance(rec.get("scope"), dict) and rec["scope"]:
            continue
        inferred = infer_default_scope(
            exp_id=str(rec.get("id") or ""),
            domain=rec.get("domain") if isinstance(rec.get("domain"), list) else None,
        )
        if inferred == MemoryScope():
            continue
        rec["scope"] = inferred.to_dict()
        updated += 1
    if updated and not dry_run:
        l4_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return {
        "ok": True,
        "path": str(l4_path),
        "updated": updated,
        "dry_run": dry_run,
        "total": len(records),
    }


__all__ = [
    "backfill_tenant_coding_scopes",
    "collect_memory_scope_stats",
    "format_memory_scope_diagnostic_lines",
    "run_memory_scope_diagnose",
]
