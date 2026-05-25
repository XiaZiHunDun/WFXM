"""Built-in skill catalog index."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from butler.registry.paths import catalog_dir
from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_types import SkillBundle, SkillSearchHit

logger = logging.getLogger(__name__)


class BundledSource(SkillSource):
    @property
    def source_id(self) -> str:
        return "bundled"

    def _entries(self) -> list[dict[str, Any]]:
        index = catalog_dir() / "skills" / "index.yaml"
        if not index.is_file():
            return []
        try:
            data = yaml.safe_load(index.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("bundled index load failed: %s", exc)
            return []
        items = data.get("skills") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict)]

    def _match(self, query: str, entry: dict[str, Any]) -> bool:
        q = query.strip().lower()
        if not q:
            return True
        name = str(entry.get("name") or "").lower()
        desc = str(entry.get("description") or "").lower()
        ident = str(entry.get("id") or entry.get("identifier") or "").lower()
        return q in name or q in desc or q in ident

    def search(self, query: str, *, limit: int = 20) -> list[SkillSearchHit]:
        hits: list[SkillSearchHit] = []
        for entry in self._entries():
            if not self._match(query, entry):
                continue
            ident = str(entry.get("id") or f"bundled:{entry.get('name')}")
            hits.append(
                SkillSearchHit(
                    name=str(entry.get("name") or ""),
                    description=str(entry.get("description") or "")[:500],
                    source=self.source_id,
                    identifier=ident,
                    trust=str(entry.get("trust") or "builtin"),
                    tags=list(entry.get("tags") or []),
                    extra={"path": entry.get("path")},
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def inspect(self, identifier: str) -> SkillSearchHit | None:
        ident = identifier.strip()
        for entry in self._entries():
            eid = str(entry.get("id") or f"bundled:{entry.get('name')}")
            if eid == ident or str(entry.get("name")) == ident:
                return SkillSearchHit(
                    name=str(entry.get("name") or ""),
                    description=str(entry.get("description") or ""),
                    source=self.source_id,
                    identifier=eid,
                    trust=str(entry.get("trust") or "builtin"),
                    tags=list(entry.get("tags") or []),
                    extra={"path": entry.get("path")},
                )
        return None

    def fetch(self, identifier: str) -> SkillBundle | None:
        meta = self.inspect(identifier)
        if meta is None:
            return None
        rel = str((meta.extra or {}).get("path") or "").strip()
        if not rel:
            return None
        root = Path(__file__).resolve().parents[3]
        src = (root / rel).resolve()
        if not src.is_file():
            logger.warning("bundled skill file missing: %s", src)
            return None
        try:
            text = src.read_text(encoding="utf-8")
        except OSError:
            return None
        return SkillBundle(
            name=meta.name,
            files={"SKILL.md": text},
            source=self.source_id,
            identifier=meta.identifier,
            trust=meta.trust,
            metadata={"path": str(src)},
        )
