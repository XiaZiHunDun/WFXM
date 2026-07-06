"""ClawHub skill source (clawhub.ai API v1 subset)."""

from __future__ import annotations

import io
import logging
import os
import re
import time
import zipfile
from typing import Any
from urllib.parse import urlparse

import httpx

from butler.registry.hub_index_cache import read_cache, write_cache
from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_sources.zip_safety import is_unsafe_zip_entry
from butler.registry.skill_types import SkillBundle, SkillSearchHit
from butler.registry.url_safety import is_safe_url

logger = logging.getLogger(__name__)

_TEXT_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml")


def clawhub_base_url() -> str:
    raw = os.getenv("BUTLER_CLAWHUB_URL", "https://clawhub.ai/api/v1").strip()
    return raw.rstrip("/")


def clawhub_enabled() -> bool:
    return os.getenv("BUTLER_CLAWHUB_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _slug_from_identifier(identifier: str) -> str:
    ident = identifier.strip()
    if ident.startswith("clawhub:"):
        ident = ident[8:]
    return ident.split("/")[-1].strip()


def _normalize_identifier(slug: str) -> str:
    return f"clawhub:{slug}"


def _safe_zip_path(name: str) -> str | None:
    normalized = name.replace("\\", "/").lstrip("/")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if not parts or ".." in parts:
        return None
    if not normalized.lower().endswith(_TEXT_SUFFIXES):
        return None
    return "/".join(parts)


class ClawHubSource(SkillSource):  # type: ignore[misc]
    """Community skills from ClawHub — always trust=community."""

    @property
    def source_id(self) -> str:
        return "clawhub"

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any | None:
        url = f"{clawhub_base_url()}{path}"
        host = (urlparse(url).hostname or "").lower()
        if host not in ("clawhub.ai", "www.clawhub.ai") and not is_safe_url(url):
            return None
        from butler.registry.skill_sources.clawhub_ops import clawhub_get_json_safe

        return clawhub_get_json_safe(url, params=params)

    def search(self, query: str, *, limit: int = 20) -> list[SkillSearchHit]:
        if not clawhub_enabled():
            return []
        q = query.strip()
        cache_key = f"clawhub_search:{q}:{limit}"
        cached = read_cache(cache_key)
        if isinstance(cached, list):
            return [SkillSearchHit(**row) for row in cached if isinstance(row, dict)]

        if q:
            slug_guess = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")
            if slug_guess and re.fullmatch(r"[a-z0-9][a-z0-9._-]*", slug_guess):
                meta = self.inspect(slug_guess)
                if meta:
                    return [meta]

        data = self._get_json("/skills", params={"search": q, "limit": limit})
        items: list[Any] = []
        if isinstance(data, dict):
            raw = data.get("items", data.get("skills", []))
            if isinstance(raw, list):
                items = raw
        elif isinstance(data, list):
            items = data

        hits: list[SkillSearchHit] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip()
            if not slug:
                continue
            hits.append(
                SkillSearchHit(
                    name=str(item.get("displayName") or item.get("name") or slug),
                    description=str(
                        item.get("summary") or item.get("description") or ""
                    )[:500],
                    source=self.source_id,
                    identifier=_normalize_identifier(slug),
                    trust="community",
                    tags=_tags_list(item.get("tags")),
                    extra={
                        "weekly_installs": item.get("weeklyInstalls"),
                        "version": _latest_version_label(item),
                    },
                )
            )

        write_cache(
            cache_key,
            [
                {
                    "name": h.name,
                    "description": h.description,
                    "source": h.source,
                    "identifier": h.identifier,
                    "trust": h.trust,
                    "tags": h.tags,
                    "extra": h.extra,
                }
                for h in hits
            ],
        )
        return hits

    def inspect(self, identifier: str) -> SkillSearchHit | None:
        if not clawhub_enabled():
            return None
        slug = _slug_from_identifier(identifier)
        if not slug:
            return None
        data = self._coerce_skill(self._get_json(f"/skills/{slug}"))
        if not isinstance(data, dict):
            return None
        return SkillSearchHit(
            name=str(data.get("displayName") or data.get("name") or slug),
            description=str(data.get("summary") or data.get("description") or ""),
            source=self.source_id,
            identifier=_normalize_identifier(str(data.get("slug") or slug)),
            trust="community",
            tags=_tags_list(data.get("tags")),
            extra={"detail_url": f"https://clawhub.ai/skills/{slug}"},
        )

    def fetch(self, identifier: str) -> SkillBundle | None:
        if not clawhub_enabled():
            return None
        slug = _slug_from_identifier(identifier)
        data = self._coerce_skill(self._get_json(f"/skills/{slug}"))
        if not isinstance(data, dict):
            return None
        version = _resolve_latest_version(slug, data, self._get_json)
        if not version:
            return None
        files = self._download_zip(slug, version)
        if "SKILL.md" not in files:
            version_data = self._get_json(f"/skills/{slug}/versions/{version}")
            if isinstance(version_data, dict):
                files.update(_extract_inline_files(version_data))
        if "SKILL.md" not in files:
            return None
        return SkillBundle(
            name=slug,
            files=files,
            source=self.source_id,
            identifier=_normalize_identifier(slug),
            trust="community",
            metadata={"version": version},
        )

    def _coerce_skill(self, data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        nested = data.get("skill")
        if isinstance(nested, dict):
            merged = dict(nested)
            if data.get("latestVersion") is not None:
                merged.setdefault("latestVersion", data.get("latestVersion"))
            return merged
        return data

    def _download_zip(self, slug: str, version: str) -> dict[str, str]:
        files: dict[str, str] = {}
        base = clawhub_base_url().replace("/api/v1", "")
        url = f"{base}/api/v1/download"
        for attempt in range(3):
            try:
                from butler.registry.url_safety import safe_registry_get

                resp = safe_registry_get(
                    url,
                    params={"slug": slug, "version": version},
                    timeout=45.0,
                )
                if resp.status_code == 429:
                    time.sleep(min(int(resp.headers.get("retry-after", "5") or 5), 15))
                    continue
                if resp.status_code != 200:
                    return files
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    for info in zf.infolist():
                        # Sprint 20-2 SEC-20-A-2: skip symlinks / FIFO / CHR / BLK / SOCK.
                        if info.is_dir() or info.file_size > 500_000:
                            continue
                        if is_unsafe_zip_entry(info):
                            continue
                        safe = _safe_zip_path(info.filename)
                        if not safe:
                            continue
                        try:
                            files[safe] = zf.read(info.filename).decode(
                                "utf-8",
                                errors="replace",
                            )
                        except (UnicodeDecodeError, KeyError):
                            continue
                return files
            except (zipfile.BadZipFile, httpx.HTTPError) as exc:
                logger.debug("clawhub zip %s@%s: %s", slug, version, exc)
                return files
        return files


def _tags_list(tags: Any) -> list[str]:
    if isinstance(tags, list):
        return [str(t) for t in tags]
    if isinstance(tags, dict):
        return [str(k) for k in tags if str(k) != "latest"]
    return []


def _latest_version_label(item: dict[str, Any]) -> str:
    latest = item.get("latestVersion")
    if isinstance(latest, dict):
        return str(latest.get("version") or "")
    if isinstance(latest, str):
        return latest
    tags = item.get("tags")
    if isinstance(tags, dict):
        return str(tags.get("latest") or "")
    return ""


def _resolve_latest_version(
    slug: str,
    skill_data: dict[str, Any],
    get_json: Any,
) -> str | None:
    latest = skill_data.get("latestVersion")
    if isinstance(latest, dict):
        v = latest.get("version")
        if isinstance(v, str) and v:
            return v
    tags = skill_data.get("tags")
    if isinstance(tags, dict):
        t = tags.get("latest")
        if isinstance(t, str) and t:
            return t
    versions = get_json(f"/skills/{slug}/versions")
    if isinstance(versions, list) and versions:
        first = versions[0]
        if isinstance(first, dict):
            v = first.get("version")
            if isinstance(v, str) and v:
                return v
    return None


def _extract_inline_files(version_data: dict[str, Any]) -> dict[str, str]:
    files: dict[str, str] = {}
    nested = version_data.get("version")
    if isinstance(nested, dict):
        version_data = nested
    raw_files = version_data.get("files")
    if isinstance(raw_files, dict):
        return {k: v for k, v in raw_files.items() if isinstance(v, str)}
    if not isinstance(raw_files, list):
        return files
    for meta in raw_files:
        if not isinstance(meta, dict):
            continue
        fname = str(meta.get("path") or meta.get("name") or "")
        if not fname:
            continue
        if isinstance(meta.get("content"), str):
            files[fname] = meta["content"]
            continue
        raw_url = meta.get("rawUrl") or meta.get("downloadUrl") or meta.get("url")
        if isinstance(raw_url, str) and raw_url.startswith("http") and is_safe_url(raw_url):
            from butler.registry.skill_sources.clawhub_ops import fetch_inline_file_text_safe

            text = fetch_inline_file_text_safe(raw_url)
            if text is not None:
                files[fname] = text
    return files
