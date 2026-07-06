"""Fetch skill from HTTPS URL (SKILL.md or raw markdown)."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_types import SkillBundle, SkillSearchHit
from butler.registry.url_safety import is_safe_url

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z][a-z0-9._-]*$")


class UrlSource(SkillSource):  # type: ignore[misc]
    @property
    def source_id(self) -> str:
        return "url"

    def search(self, query: str, *, limit: int = 20) -> list[SkillSearchHit]:
        q = query.strip()
        if q.startswith("http://") or q.startswith("https://"):
            if is_safe_url(q):
                return [
                    SkillSearchHit(
                        name=_guess_name(q),
                        description=f"URL skill: {q[:120]}",
                        source=self.source_id,
                        identifier=q,
                        trust="community",
                        extra={"url": q},
                    )
                ]
        return []

    def inspect(self, identifier: str) -> SkillSearchHit | None:
        if not identifier.startswith("http"):
            return None
        if not is_safe_url(identifier):
            return None
        return SkillSearchHit(
            name=_guess_name(identifier),
            description=f"URL: {identifier[:200]}",
            source=self.source_id,
            identifier=identifier,
            trust="community",
            extra={"url": identifier},
        )

    def fetch(self, identifier: str) -> SkillBundle | None:
        url = identifier.strip()
        if not is_safe_url(url):
            return None
        from butler.registry.skill_sources.url_ops import fetch_url_skill_text_safe

        text = fetch_url_skill_text_safe(url)
        if text is None:
            return None
        name = _guess_name(url)
        return SkillBundle(
            name=name,
            files={"SKILL.md": text},
            source=self.source_id,
            identifier=url,
            trust="community",
            metadata={"url": url, "awaiting_name": not _NAME_RE.match(name)},
        )


def _guess_name(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    stem = path.split("/")[-1] if path else "url-skill"
    stem = re.sub(r"\.(md|markdown|txt)$", "", stem, flags=re.I)
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem.lower()).strip("-")
    if stem and _NAME_RE.match(stem):
        return stem[:64]
    return "url-skill"
