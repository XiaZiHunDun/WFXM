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
    "list_template_ids",
    "load_template",
    "validate_slug",
    "write_project_yaml",
]
