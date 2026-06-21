"""Sync registry-installed tenant skills into a project ``.butler/skills/``."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from butler.registry.paths import skills_root
from butler.registry.skill_lock import SkillLockFile
from butler.registry.skill_types import InstalledSkillRecord
from butler.skills.layout import (
    _copy_tree_allowed_files,
    _skill_md_in_dir,
    directory_content_rel,
    write_directory_stub,
)

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)


def _parse_stub_frontmatter(text: str) -> dict[str, Any]:
    m = _FRONTMATTER.match(text)
    if not m:
        return {}
    try:
        fm = yaml.safe_load(m.group(1)) or {}
        return fm if isinstance(fm, dict) else {}
    except yaml.YAMLError:
        return {}


def _stack_skill_names(workspace: Path) -> list[str]:
    stack = workspace / "stack.yaml"
    if not stack.is_file():
        return []
    try:
        data = yaml.safe_load(stack.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    skills = data.get("skills")
    if not isinstance(skills, dict):
        return []
    expected = skills.get("skills_expected")
    if isinstance(expected, list):
        return [str(x).strip() for x in expected if str(x).strip()]
    return []


def _resolve_sync_names(
    workspace: Path,
    *,
    tenant_id: str,
    only: list[str] | None,
) -> list[str]:
    lock = SkillLockFile(tenant_id=tenant_id)
    locked = {rec.name for rec in lock.list_installed()}
    if only:
        return [n for n in only if n in locked]
    from_stack = _stack_skill_names(workspace)
    if from_stack:
        return [n for n in from_stack if n in locked]
    return sorted(locked)


def _copy_one_skill(src_root: Path, dest_root: Path, name: str) -> tuple[bool, str]:
    dest_root.mkdir(parents=True, exist_ok=True)
    stub = src_root / f"{name}.md"
    skill_dir = src_root / name

    if stub.is_file():
        text = stub.read_text(encoding="utf-8")
        fm = _parse_stub_frontmatter(text)
        if str(fm.get("install_type") or "") == "directory":
            content_rel = str(fm.get("content_path") or directory_content_rel(name)).strip()
            dest_stub = dest_root / f"{name}.md"
            shutil.copy2(stub, dest_stub)
            inner = src_root / content_rel
            if not inner.is_file() and skill_dir.is_dir():
                _copy_tree_allowed_files(skill_dir, dest_root / name)
                file_count = sum(1 for p in (dest_root / name).rglob("*") if p.is_file())
                return True, f"{name}: directory ({file_count} files)"
            if skill_dir.is_dir():
                dest_sub = dest_root / name
                if dest_sub.exists():
                    shutil.rmtree(dest_sub)
                _copy_tree_allowed_files(skill_dir, dest_sub)
            elif inner.is_file():
                dest_inner = dest_root / content_rel
                dest_inner.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(inner, dest_inner)
            file_count = sum(1 for p in (dest_root / name).rglob("*") if p.is_file()) if (dest_root / name).is_dir() else 0
            return True, f"{name}: directory ({file_count} files)"

        shutil.copy2(stub, dest_root / f"{name}.md")
        return True, f"{name}: flat"

    if skill_dir.is_dir():
        inner = _skill_md_in_dir(skill_dir)
        if inner is None:
            return False, f"{name}: missing SKILL.md in tenant"
        dest_sub = dest_root / name
        if dest_sub.exists():
            shutil.rmtree(dest_sub)
        _copy_tree_allowed_files(skill_dir, dest_sub)
        inner_rel = inner.relative_to(skill_dir).as_posix()
        desc = ""
        try:
            fm = _parse_stub_frontmatter(inner.read_text(encoding="utf-8"))
            desc = str(fm.get("description") or "")[:1024]
        except OSError:
            pass
        write_directory_stub(
            dest_root,
            name,
            description=desc,
            content_rel=directory_content_rel(name, inner_rel),
        )
        file_count = sum(1 for p in dest_sub.rglob("*") if p.is_file())
        return True, f"{name}: directory ({file_count} files)"

    return False, f"{name}: not found in tenant skills"


def sync_tenant_skills_to_project(
    workspace: str | Path,
    *,
    tenant_id: str = "default",
    only: list[str] | None = None,
    dry_run: bool = False,
) -> tuple[bool, str, list[str]]:
    """Copy lockfile-managed tenant skills into ``<workspace>/.butler/skills/``."""
    ws = Path(workspace).expanduser().resolve()
    dest = ws / ".butler" / "skills"
    src = skills_root(tenant_id=tenant_id)
    names = _resolve_sync_names(ws, tenant_id=tenant_id, only=only)
    if not names:
        return False, "无可同步的 registry 技能（lockfile 为空或与 stack 无交集）", []

    actions: list[str] = []
    errors: list[str] = []
    for name in names:
        if dry_run:
            actions.append(f"[dry-run] {name}")
            continue
        ok, detail = _copy_one_skill(src, dest, name)
        if ok:
            actions.append(detail)
        else:
            errors.append(detail)

    if dry_run:
        return True, f"[dry-run] 将同步 {len(names)} 项 → {dest}", actions
    if errors and not actions:
        return False, "同步失败:\n" + "\n".join(errors), actions
    msg = f"已同步 {len(actions)} 项 → {dest}"
    if errors:
        msg += "\n跳过:\n" + "\n".join(errors)
    return True, msg, actions


def skill_auto_sync_project_enabled() -> bool:
    return os.getenv("BUTLER_SKILL_AUTO_SYNC_PROJECT", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def resolve_default_project_workspace() -> Path | None:
    """Workspace for ``BUTLER_DEFAULT_PROJECT`` when ``stack.yaml`` exists."""
    name = os.getenv("BUTLER_DEFAULT_PROJECT", "").strip()
    if not name:
        try:
            from butler.config import load_settings

            name = str(load_settings().default_project or "").strip()
        except Exception:
            name = ""
    if not name:
        return None
    try:
        from butler.project.manager import get_project_manager

        project = get_project_manager().get_project(name)
        workspace = getattr(project, "workspace", None) if project is not None else None
        if not workspace:
            return None
        ws = Path(str(workspace)).expanduser().resolve()
        if (ws / "stack.yaml").is_file():
            return ws
    except Exception:
        return None
    return None


def maybe_sync_after_registry_install(
    record: InstalledSkillRecord,
    *,
    tenant_id: str = "default",
) -> str:
    """Auto-sync or hint project copy after registry install/upgrade."""
    ws = resolve_default_project_workspace()
    if ws is None:
        return ""
    if skill_auto_sync_project_enabled():
        ok, msg, actions = sync_tenant_skills_to_project(
            ws,
            tenant_id=tenant_id,
            only=[record.name],
        )
        if ok and actions:
            return f"已同步到项目: {', '.join(actions)}"
        if not ok:
            return f"项目同步跳过: {msg}"
        return ""
    return (
        f"建议同步到项目: butler skills sync --project {ws} "
        f"--only {record.name}"
    )


__all__ = [
    "maybe_sync_after_registry_install",
    "resolve_default_project_workspace",
    "skill_auto_sync_project_enabled",
    "sync_tenant_skills_to_project",
]
