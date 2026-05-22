"""Load project.yaml archetype templates and bootstrap workspace files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = _REPO_ROOT / "docs" / "templates" / "project-archetypes"

_TEMPLATE_FILES = {
    "software-default": "software-default.project.yaml",
    "novel-factory": "novel-factory.project.yaml",
    "knowledge-light": "knowledge-light.project.yaml",
}

_RUNTIME_TEMPLATE_FILES = {
    "software-default": "software-default.runtime.jobs.yaml",
}

_SLUG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")

_MEMORY_TEMPLATE = """# 项目记忆

## Decisions

## Notes
"""


def validate_slug(slug: str) -> tuple[bool, str]:
    s = (slug or "").strip()
    if not s:
        return False, "目录 slug 不能为空"
    if not _SLUG_RE.match(s):
        return (
            False,
            "slug 须为 ASCII 字母开头，仅含字母、数字、_-（微信显示名请写在 name 字段）",
        )
    return True, ""


def list_template_ids() -> list[str]:
    return sorted(_TEMPLATE_FILES.keys())


def load_template(template_id: str) -> dict[str, Any]:
    key = (template_id or "software-default").strip()
    fname = _TEMPLATE_FILES.get(key)
    if not fname:
        raise ValueError(
            f"未知模板 {template_id!r}，可选: {', '.join(list_template_ids())}"
        )
    path = _TEMPLATES_DIR / fname
    if not path.is_file():
        raise FileNotFoundError(f"模板文件不存在: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"模板格式无效: {path}")
    return data


def ensure_memory_skeleton(workspace: Path) -> Path:
    mem = workspace / ".butler" / "memory" / "MEMORY.md"
    if mem.is_file():
        return mem
    mem.parent.mkdir(parents=True, exist_ok=True)
    mem.write_text(_MEMORY_TEMPLATE, encoding="utf-8")
    return mem


def ensure_runtime_jobs_skeleton(
    workspace: Path,
    project_name: str,
    template_id: str,
) -> Path | None:
    """Write ``runtime/jobs.yaml`` from template if missing (software-default only)."""
    key = (template_id or "").strip()
    fname = _RUNTIME_TEMPLATE_FILES.get(key)
    if not fname:
        return None
    jobs_path = workspace / "runtime" / "jobs.yaml"
    if jobs_path.is_file():
        return jobs_path
    src = _TEMPLATES_DIR / fname
    if not src.is_file():
        return None
    text = src.read_text(encoding="utf-8")
    text = text.replace("project: 项目名称", f"project: {project_name}", 1)
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(text, encoding="utf-8")
    return jobs_path


def reindex_project_memory(project_name: str) -> tuple[bool, str]:
    """Rebuild semantic index for one project. Returns (ok, message)."""
    from butler.config import get_butler_home
    from butler.memory.reindex import ensure_semantic_enabled_msg, reindex_semantic_memory

    hint = ensure_semantic_enabled_msg()
    if hint:
        return False, hint
    result = reindex_semantic_memory(
        get_butler_home(),
        project_name=project_name.strip(),
        index_experience=False,
        index_project_memory=True,
        clear_vectors=False,
    )
    if not result.get("ok"):
        return False, str(result.get("error") or "reindex failed")
    n = int(result.get("indexed_project_bullets") or 0)
    return True, f"已索引项目 MEMORY {n} 条"


def write_project_yaml(
    workspace: Path,
    data: dict[str, Any],
    *,
    merge_existing: bool = False,
) -> Path:
    cfg = workspace / "project.yaml"
    if merge_existing and cfg.is_file():
        existing = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        if isinstance(existing, dict):
            for k, v in data.items():
                if k not in existing or existing[k] in (None, "", []):
                    existing[k] = v
            data = existing
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return cfg


__all__ = [
    "ensure_memory_skeleton",
    "ensure_runtime_jobs_skeleton",
    "list_template_ids",
    "load_template",
    "reindex_project_memory",
    "validate_slug",
    "write_project_yaml",
]
