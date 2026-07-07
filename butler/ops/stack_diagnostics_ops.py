"""Stack diagnostics best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def load_stack_safe(path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any] | None:
        if not path.is_file():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None

    return safe_best_effort(_run, label="stack_diagnostics.load_stack", default=None)


def tenant_id_default_safe() -> str:
    def _run() -> str:
        from butler.config import load_settings

        return load_settings().default_tenant

    result = safe_best_effort(_run, label="stack_diagnostics.tenant_id", default="default")
    return str(result or "default")


def tenant_skill_paths_safe(skill_name: str, *, tenant_id: str) -> bool:
    def _run() -> bool:
        from butler.registry.paths import skills_root

        tenant_root = skills_root(tenant_id=tenant_id)
        if (tenant_root / f"{skill_name}.md").is_file():
            return True
        return (tenant_root / skill_name / "SKILL.md").is_file()

    result = safe_best_effort(_run, label="stack_diagnostics.tenant_skill", default=False)
    return bool(result)


def skill_lock_by_name_safe(tenant_id: str) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.registry.skill_lock import SkillLockFile

        return {rec.name: rec for rec in SkillLockFile(tenant_id=tenant_id).list_installed()}

    result = safe_best_effort(_run, label="stack_diagnostics.skill_lock", default={})
    return result if isinstance(result, dict) else {}


def check_directory_skill_layouts_safe(
    names: list[Any],
    *,
    workspace: Path,
    tenant_id: str,
    out: dict[str, Any],
) -> None:
    def _run() -> None:
        from butler.registry.marketplace_compat import check_directory_skill_layout

        for name in names:
            ok_layout, detail = check_directory_skill_layout(
                str(name), workspace=workspace, tenant_id=tenant_id
            )
            if ok_layout:
                out["checks"].append(f"skill:{name}:directory={detail}")
            elif detail == "missing":
                pass
            elif detail == "flat":
                out["warnings"].append(
                    f"skill [{name}] 为单文件安装，建议 "
                    f"`butler skills upgrade {name}` 后 "
                    f"`butler skills sync --project {workspace}`"
                )
                out["ok"] = False
            else:
                out["warnings"].append(f"skill [{name}] 目录布局异常: {detail}")
                out["ok"] = False

    safe_best_effort(_run, label="stack_diagnostics.directory_layout", default=None)


def check_plugin_adoption_safe(adoption: dict[str, Any], out: dict[str, Any]) -> None:
    def _run() -> None:
        from butler.registry.marketplace_compat import (
            format_adoption_lines,
            missing_mcp_suggestions,
        )

        for line in format_adoption_lines(adoption):
            out["checks"].append(f"adoption:{line}")
        suggested = adoption.get("mcp_suggested")
        if not isinstance(suggested, list):
            adopted = adoption.get("adopted")
            if isinstance(adopted, dict):
                suggested = adopted.get("mcp")
        if isinstance(suggested, list):
            for warn in missing_mcp_suggestions(adoption):
                out["warnings"].append(warn)

    safe_best_effort(_run, label="stack_diagnostics.plugin_adoption", default=None)


def check_ingest_stats_safe(ws: Path, out: dict[str, Any]) -> None:
    def _run() -> None:
        from butler.memory.document_ingest import ingest_stats

        stats = ingest_stats(ws)
        if stats.get("enabled"):
            out["checks"].append(f"ingest:enabled md={stats.get('md_files', 0)}")
        elif stats.get("md_files", 0) > 0:
            out["checks"].append(f"ingest:cache md={stats.get('md_files', 0)}")
        else:
            out["warnings"].append(
                "EXT-3 未启用（BUTLER_INGEST_ENABLED=0）且无 ingest 缓存；"
                "参考书需 butler memory ingest"
            )

    safe_best_effort(_run, label="stack_diagnostics.ingest_stats", default=None)
