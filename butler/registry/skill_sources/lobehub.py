"""LobeHub Skills Marketplace adapter (API token or market-cli)."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import zipfile
from typing import Any, cast

from butler.registry.hub_index_cache import read_cache, write_cache
from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_sources.zip_safety import is_unsafe_zip_entry
from butler.registry.skill_types import SkillBundle, SkillSearchHit
from butler.registry.url_safety import is_safe_url

logger = logging.getLogger(__name__)

_TEXT_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml")


def lobehub_enabled() -> bool:
    return os.getenv("BUTLER_LOBEHUB_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def lobehub_base_url() -> str:
    return os.getenv("BUTLER_LOBEHUB_URL", "https://market.lobehub.com").strip().rstrip("/")


def lobehub_token() -> str:
    return os.getenv("BUTLER_LOBEHUB_TOKEN", "").strip()


def lobehub_prefer_cli() -> bool:
    return os.getenv("BUTLER_LOBEHUB_USE_CLI", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _normalize_identifier(slug: str) -> str:
    return f"lobehub:{slug}"


def _parse_identifier(identifier: str) -> str:
    ident = identifier.strip()
    for prefix in ("lobehub:", "lobehub-"):
        if ident.startswith(prefix):
            return ident[len(prefix) :]
    return ident


def _api_headers() -> dict[str, str]:
    token = lobehub_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _safe_zip_path(name: str) -> str | None:
    normalized = name.replace("\\", "/").lstrip("/")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if not parts or ".." in parts:
        return None
    if not normalized.lower().endswith(_TEXT_SUFFIXES):
        return None
    return "/".join(parts)


def _item_to_hit(item: dict[str, Any]) -> SkillSearchHit | None:
    ident = str(item.get("identifier") or "").strip()
    if not ident:
        return None
    name = str(item.get("name") or ident.split("/")[-1])
    return SkillSearchHit(
        name=name,
        description=str(item.get("description") or "")[:500],
        source="lobehub",
        identifier=_normalize_identifier(ident),
        trust="community",
        tags=[str(t) for t in (item.get("tags") or []) if t],
        extra={
            "installCount": item.get("installCount"),
            "version": item.get("version"),
            "category": item.get("category"),
        },
    )


def _search_api(query: str, *, limit: int) -> list[SkillSearchHit]:
    token = lobehub_token()
    if not token:
        return []
    url = f"{lobehub_base_url()}/api/v1/skills"
    if not is_safe_url(url):
        return []
    from butler.registry.skill_sources.lobehub_ops import lobehub_search_api_json_safe

    data = lobehub_search_api_json_safe(
        url,
        params={
            "q": query,
            "page": 1,
            "pageSize": min(limit, 50),
            "locale": os.getenv("BUTLER_LOBEHUB_LOCALE", "zh-CN"),
        },
        headers=_api_headers(),
    )
    if data is None:
        return []

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    hits: list[SkillSearchHit] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            hit = _item_to_hit(item)
            if hit:
                hits.append(hit)
    return hits


def _run_market_cli(args: list[str], *, timeout: float = 90.0) -> dict[str, Any] | None:
    cmd = ["npx", "-y", "@lobehub/market-cli", *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("lobehub cli: %s", exc)
        return None
    if proc.returncode != 0:
        logger.debug("lobehub cli stderr: %s", (proc.stderr or "")[:200])
        return None
    out = (proc.stdout or "").strip()
    if not out:
        return None
    try:
        data = json.loads(out)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _search_cli(query: str, *, limit: int) -> list[SkillSearchHit]:
    data = _run_market_cli(
        [
            "skills",
            "search",
            "--q",
            query,
            "--page-size",
            str(min(limit, 50)),
            "--output",
            "json",
            "--locale",
            os.getenv("BUTLER_LOBEHUB_LOCALE", "zh-CN"),
        ]
    )
    if not data:
        return []
    items = data.get("items")
    if not isinstance(items, list):
        return []
    hits: list[SkillSearchHit] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            hit = _item_to_hit(item)
            if hit:
                hits.append(hit)
    return hits


def _download_zip(identifier: str) -> bytes | None:
    token = lobehub_token()
    url = f"{lobehub_base_url()}/api/v1/skills/{identifier}/download"
    if not is_safe_url(url):
        return None
    headers = _api_headers() if token else {}
    from butler.registry.skill_sources.lobehub_ops import lobehub_download_bytes_safe

    return cast(bytes | None, lobehub_download_bytes_safe(url, headers=headers))


def _fetch_cli(identifier: str) -> dict[str, str] | None:
    data = _run_market_cli(
        ["skills", "download", identifier, "--output", "json"],
        timeout=120.0,
    )
    if not isinstance(data, dict):
        return None
    files = data.get("files")
    if isinstance(files, dict):
        return {k: str(v) for k, v in files.items() if isinstance(v, str)}
    return None


def _extract_zip_files(content: bytes) -> dict[str, str]:
    files: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
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
                    files[safe] = zf.read(info.filename).decode("utf-8", errors="replace")
                except (UnicodeDecodeError, KeyError):
                    continue
    except zipfile.BadZipFile:
        return files
    return files


class LobeHubSource(SkillSource):  # type: ignore[misc]
    @property
    def source_id(self) -> str:
        return "lobehub"

    def _search_impl(self, query: str, *, limit: int) -> list[SkillSearchHit]:
        cache_key = f"lobehub_search:{query}:{limit}"
        cached = read_cache(cache_key, tenant_id="__global__")
        if isinstance(cached, list):
            return [SkillSearchHit(**row) for row in cached if isinstance(row, dict)]

        hits: list[SkillSearchHit] = []
        if lobehub_prefer_cli() or not lobehub_token():
            hits = _search_cli(query, limit=limit)
        if not hits and lobehub_token():
            hits = _search_api(query, limit=limit)
        if not hits and not lobehub_prefer_cli() and not lobehub_token():
            hits = _search_cli(query, limit=limit)

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
            tenant_id="__global__",
        )
        return hits

    def search(self, query: str, *, limit: int = 20) -> list[SkillSearchHit]:
        if not lobehub_enabled():
            return []
        q = query.strip()
        if not q:
            return []
        slug = re.sub(r"[^a-z0-9._/-]+", "-", q.lower()).strip("-")
        if slug and "/" in slug:
            hit = self.inspect(slug)
            if hit:
                return [hit]
        return self._search_impl(q, limit=limit)

    def inspect(self, identifier: str) -> SkillSearchHit | None:
        if not lobehub_enabled():
            return None
        slug = _parse_identifier(identifier)
        if not slug:
            return None
        hits = self._search_impl(slug, limit=5)
        for hit in hits:
            if hit.identifier == _normalize_identifier(slug) or slug in hit.identifier:
                return hit
        if hits:
            return hits[0]
        return SkillSearchHit(
            name=slug.split("/")[-1],
            description=f"LobeHub skill {slug}",
            source=self.source_id,
            identifier=_normalize_identifier(slug),
            trust="community",
        )

    def fetch(self, identifier: str) -> SkillBundle | None:
        if not lobehub_enabled():
            return None
        slug = _parse_identifier(identifier)
        if not slug:
            return None

        files: dict[str, str] = {}
        if lobehub_prefer_cli() or not lobehub_token():
            files = _fetch_cli(slug) or {}
        if not files:
            blob = _download_zip(slug)
            if blob:
                files = _extract_zip_files(blob)
        if not files and not lobehub_prefer_cli():
            files = _fetch_cli(slug) or {}

        if "SKILL.md" not in files and "skill.md" not in files:
            for key, val in list(files.items()):
                if key.endswith(".md"):
                    files.setdefault("SKILL.md", val)
                    break
        if "SKILL.md" not in files:
            return None

        name = slug.split("/")[-1]
        name = re.sub(r"[^a-z0-9._-]+", "-", name.lower())[:64]
        return SkillBundle(
            name=name,
            files=files,
            source=self.source_id,
            identifier=_normalize_identifier(slug),
            trust="community",
            metadata={"lobehub_identifier": slug},
        )
