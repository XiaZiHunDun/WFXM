from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

from butler.memory.butler_memory_ops import (
    close_memory_store,
    delete_experience_vector,
    open_semantic_index,
    seed_bundled_tenant_skills,
)
from butler.memory.semantic_index import (
    SOURCE_OWNER_PROFILE,
    index_experience_row,
)
from butler.memory.vector_sync_telemetry import record_vector_sync
from butler.memory.experience_consolidation import (
    digest_experience_add,
    experience_merge_enabled,
)
from butler.memory.triplets import TripletIndex
from butler.utilities.tenant import (
    DEFAULT_TENANT,
    migrate_legacy_memory_layout,
    normalize_tenant_id,
    tenant_memory_dir,
)
from butler.defaults.env_defaults import EXPERIENCE_PRUNE_DAYS_DEFAULT

from .experience_store import ExperienceStore
from .profile_store import ProfileStore

logger = logging.getLogger(__name__)


class ButlerMemory:
    """Tenant-scoped Butler memory: owner profile + cross-project experience."""

    def __init__(self, butler_home: Path, *, tenant_id: str = "default"):
        self.butler_home = Path(butler_home).expanduser().resolve()
        self.tenant_id = normalize_tenant_id(tenant_id or DEFAULT_TENANT)
        migrate_legacy_memory_layout(self.butler_home)

        seed_bundled_tenant_skills(self.butler_home, self.tenant_id)
        mem_dir = tenant_memory_dir(self.butler_home, self.tenant_id)
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.profile = ProfileStore(mem_dir / "profile.json")
        self.experience = ExperienceStore(mem_dir / "experience.db")
        self.semantic = None

        self.semantic = open_semantic_index(mem_dir)
        self._maybe_prune_stale_conversations()

    def _maybe_prune_stale_conversations(self) -> None:
        raw = os.getenv("BUTLER_EXPERIENCE_PRUNE_DAYS", EXPERIENCE_PRUNE_DAYS_DEFAULT).strip()
        if raw in ("0", "off", "false", "no"):
            return
        try:
            days = float(raw)
        except ValueError:
            days = 30.0
        result = self.prune_conversation_older_than(days)
        if int(result.get("removed_rows") or 0):
            logger.info(
                "Pruned %d stale conversation experience row(s), %d vector(s)",
                int(result.get("removed_rows") or 0),
                int(result.get("removed_vectors") or 0),
            )

    def purge_experience_vectors(self, row_ids: list[int]) -> int:
        """Delete ``experience`` source vectors for the given experience row ids."""
        sem = self.semantic
        if sem is None or not row_ids:
            return 0

        removed = 0
        for rid in row_ids:
            if delete_experience_vector(sem, rid):
                removed += 1
        return removed

    def delete_conversation_for_session(self, session_tag: str) -> dict[str, int]:
        """Purge session conversation rows and sync derivative vectors."""
        removed, ids = self.experience.delete_conversation_for_session(session_tag)
        vec = self.purge_experience_vectors(ids)
        return {"removed_rows": removed, "removed_vectors": vec}

    def prune_conversation_older_than(self, max_age_days: float = 30.0) -> dict[str, int]:
        """Purge stale conversation rows and sync derivative vectors."""
        removed, ids = self.experience.prune_conversation_older_than(max_age_days)
        vec = self.purge_experience_vectors(ids)
        return {"removed_rows": removed, "removed_vectors": vec}

    @classmethod
    def default(cls, *, tenant_id: str = "default") -> ButlerMemory:
        return cls(Path.home() / ".butler", tenant_id=tenant_id)

    def get_system_context(self, current_project: str = "") -> str:
        parts: list[str] = []
        profile_text = self.profile.format_for_prompt()
        if profile_text:
            parts.append(f"## Owner profile & preferences\n{profile_text}")

        recent = [
            r for r in self.experience.get_recent(limit=20)
            if (r.get("category") or "") != "conversation"
        ][:5]
        if recent:
            lines = [
                f"- [{r['project'] or 'global'}] ({r['category'] or 'general'}) {r['content']}"
                for r in recent
            ]
            parts.append("## Recent cross-project experience\n" + "\n".join(lines))

        if current_project.strip():
            relevant = [
                r
                for r in self.experience.search(
                    current_project.strip(), project=None, limit=5
                )
                if (r.get("category") or "") != "conversation"
            ]
            if relevant:
                rel_lines = [
                    f"- [{r['project']}] {r['content']}" for r in relevant
                ]
                parts.append("## Experience relevant to current project\n" + "\n".join(rel_lines))

        if not parts:
            return "(No Butler-level memory yet.)"
        return "\n\n".join(parts)

    def _append_experience_row(
        self,
        project: str,
        category: str,
        content: str,
        tags: str | list[str] | None = None,
    ) -> int:
        row_id = self.experience.add(project, category, content, tags=tags)
        if row_id > 0:
            index_experience_row(
                self.semantic,
                row_id,
                project=project or "",
                category=category or "",
                content=content,
            )
        return row_id

    def add_experience(
        self,
        project: str,
        category: str,
        content: str,
        tags: str | list[str] | None = None,
    ) -> int:
        """Write experience row and sync semantic index when enabled."""
        if experience_merge_enabled():
            return cast(
                int,
                digest_experience_add(
                    self, project, category, content, tags=tags,
                ),
            )
        return self._append_experience_row(project, category, content, tags=tags)

    def close(self) -> None:
        """Release sqlite connections held by experience and semantic stores."""
        close_memory_store(self.experience)
        close_memory_store(self.semantic)

    def sync_profile_vectors(self) -> int:
        """Rebuild owner_profile rows in the vector index from profile.json."""
        sem = self.semantic
        if sem is None:
            return 0

        cleared = sem.delete_source_prefix(SOURCE_OWNER_PROFILE)
        indexed = 0
        entries = list(getattr(self.profile, "_entries", []) or [])
        for idx, entry in enumerate(entries):
            text = str(entry).strip()
            if not text:
                continue
            sem.upsert(
                source=SOURCE_OWNER_PROFILE,
                source_id=f"entry:{idx}",
                content=text,
                project="",
                category="profile",
            )
            indexed += 1
        logger.debug("Profile vectors: cleared %d, indexed %d", cleared, indexed)
        if indexed > 0:
            record_vector_sync("owner_profile")
        return indexed

    def search_profile_vectors(self, query: str, *, limit: int = 4) -> list[dict[str, Any]]:
        if self.semantic is None:
            return []
        return cast(list[dict[str, Any]], self.semantic.search_owner_profile(query, limit=limit))

    def triplet_index(self) -> Any:
        if self.semantic is None:
            return None
        return TripletIndex(self.semantic.db_path)
