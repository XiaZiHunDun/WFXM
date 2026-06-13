"""Memory scope for multi-project coding experiences (L3 project + L4 tenant)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Visibility = Literal["private", "global", "stack"]
ScopeLevel = Literal["tenant", "project"]

# Tenant-level B9 entries that are LingWen1-specific until migrated to L3.
_LINGWEN_PRIVATE_EXP_IDS: frozenset[str] = frozenset(
    {
        "B9_EX_prod_lingwen_demo_add",
        "B9_EX_prod_lingwen_workflow_guard",
    }
)
LINGWEN1_PROJECT_ID = "灵文1号"


def delegate_project_id(project: Any | None) -> str:
    """Registered project name for MemoryScope matching."""
    if project is None:
        return ""
    return str(getattr(project, "name", "") or "").strip()


def stack_tags_for_project(project: Any | None) -> frozenset[str]:
    """Lowercase tags for visibility=stack retrieval (pack, type, layout)."""
    if project is None:
        return frozenset()
    tags: list[str] = []
    pack = str(getattr(project, "pack", "") or "").strip()
    ptype = str(getattr(project, "type", "") or "").strip()
    if pack:
        tags.append(pack)
    if ptype:
        tags.append(ptype)
    ws = getattr(project, "workspace", None)
    if ws is not None:
        root = Path(ws).expanduser().resolve()
        if (root / "novel-factory").is_dir():
            tags.append("novel-factory")
    return frozenset(t.lower() for t in tags if t)


def tenant_coding_experiences_path(butler_home: str | Path) -> Path:
    return Path(butler_home).expanduser().resolve() / "coding_experiences.json"


def coding_experiences_save_path(
    *,
    butler_home: str | Path,
    project: Any | None,
) -> Path:
    """L3 when project workspace is known, else L4 tenant corpus."""
    if project is not None and getattr(project, "workspace", None):
        return project_coding_experiences_path(project.workspace)
    return tenant_coding_experiences_path(butler_home)


def load_delegate_experience_library(
    *,
    butler_home: str | Path,
    project: Any | None,
    theorem_lib: Any,
) -> Any:
    """L4 tenant corpus merged with L3 project file for dev delegate retrieval."""
    from butler.dev_engine.coding_knowledge import ExperienceLibrary

    workspace = None
    if project is not None and getattr(project, "workspace", None):
        workspace = str(project.workspace)
    xlib = ExperienceLibrary.load_merged_for_project(
        tenant_path=str(tenant_coding_experiences_path(butler_home)),
        project_workspace=workspace,
        theorem_lib=theorem_lib,
    )
    if not xlib._experiences:
        xlib.load_seed_if_empty()
    return xlib


def scope_for_extracted_experience(project: Any | None) -> MemoryScope:
    """New dev-extracted rows default to L3 private for the active project."""
    pid = delegate_project_id(project)
    if pid and project is not None and getattr(project, "workspace", None):
        return MemoryScope(
            level="project",
            project_id=pid,
            visibility="private",
            source="mining",
        )
    return MemoryScope(level="tenant", visibility="global", source="mining")


@dataclass(frozen=True)
class MemoryScope:
    """Where an experience lives and who may retrieve it during dev delegate."""

    level: ScopeLevel = "tenant"
    project_id: str = ""
    visibility: Visibility = "global"
    stack_tags: tuple[str, ...] = ()
    source: str = "manual"

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "project_id": self.project_id,
            "visibility": self.visibility,
            "stack_tags": list(self.stack_tags),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> MemoryScope:
        if not isinstance(raw, dict):
            return cls()
        tags = raw.get("stack_tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return cls(
            level=str(raw.get("level") or "tenant"),  # type: ignore[arg-type]
            project_id=str(raw.get("project_id") or "").strip(),
            visibility=str(raw.get("visibility") or "global"),  # type: ignore[arg-type]
            stack_tags=tuple(str(t).strip() for t in tags if str(t).strip()),
            source=str(raw.get("source") or "manual").strip() or "manual",
        )

    def visible_to(
        self,
        *,
        project_id: str = "",
        stack_tags: frozenset[str] | set[str] | None = None,
    ) -> bool:
        """Whether this experience may be injected for a delegate in *project_id*."""
        if self.visibility == "global":
            return True
        pid = (project_id or "").strip()
        if self.visibility == "private":
            return bool(pid) and pid == (self.project_id or "").strip()
        if self.visibility == "stack":
            want = stack_tags or frozenset()
            if not want:
                return False
            have = frozenset(self.stack_tags)
            return bool(have & frozenset(want))
        return False


def project_coding_experiences_path(workspace: Path | str) -> Path:
    """L3 SSOT: per-project dev experience file."""
    return Path(workspace).expanduser().resolve() / ".butler" / "memory" / "coding_experiences.json"


def infer_default_scope(*, exp_id: str, domain: list[str] | None = None) -> MemoryScope:
    """Backfill scope for legacy tenant corpus rows (P0 migration)."""
    eid = (exp_id or "").strip()
    dom = [str(d).lower() for d in (domain or [])]
    if eid in _LINGWEN_PRIVATE_EXP_IDS or "prod_lingwen" in eid:
        return MemoryScope(
            level="tenant",
            project_id=LINGWEN1_PROJECT_ID,
            visibility="private",
            source="b9",
        )
    if eid.startswith("B9_") or "b9" in dom:
        return MemoryScope(level="tenant", visibility="global", source="b9")
    return MemoryScope(level="tenant", visibility="global")


def backfill_experience_scope(exp: Any) -> bool:
    """Ensure *exp* (CodingExperience) has explicit scope; return True if mutated."""
    from butler.dev_engine.coding_knowledge import CodingExperience

    if not isinstance(exp, CodingExperience):
        return False
    current = getattr(exp, "scope", None)
    if isinstance(current, MemoryScope) and (
        current.visibility != "global"
        or current.project_id
        or current.stack_tags
        or current.source != "manual"
    ):
        return False
    # Legacy rows: default global with no project — infer from id/domain.
    inferred = infer_default_scope(exp_id=exp.id, domain=exp.domain)
    if inferred == MemoryScope():
        return False
    exp.scope = inferred
    return True


__all__ = [
    "LINGWEN1_PROJECT_ID",
    "MemoryScope",
    "Visibility",
    "ScopeLevel",
    "backfill_experience_scope",
    "coding_experiences_save_path",
    "delegate_project_id",
    "infer_default_scope",
    "load_delegate_experience_library",
    "project_coding_experiences_path",
    "scope_for_extracted_experience",
    "stack_tags_for_project",
    "tenant_coding_experiences_path",
]
