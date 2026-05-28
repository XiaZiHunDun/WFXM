"""Remote MCP catalog indexes (MCP-P2 custom_url)."""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from butler.registry.hub_index_cache import read_cache, write_cache
from butler.registry.mcp_catalog import McpCatalogEntry
from butler.registry.url_safety import is_safe_url

logger = logging.getLogger(__name__)


def remote_catalog_enabled() -> bool:
    return bool(os.getenv("BUTLER_MCP_CATALOG_URLS", "").strip())


def _parse_catalog_payload(data: Any) -> list[McpCatalogEntry]:
    if not isinstance(data, dict):
        return []
    rows = data.get("servers")
    if not isinstance(rows, list):
        return []
    out: list[McpCatalogEntry] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        out.append(
            McpCatalogEntry(
                id=str(row["id"]),
                title=str(row.get("title") or row["id"]),
                description=str(row.get("description") or ""),
                trust=str(row.get("trust") or "community"),
                transport=str(row.get("transport") or "stdio"),
                command=str(row.get("command") or ""),
                args=[str(a) for a in (row.get("args") or [])],
                url=str(row.get("url") or ""),
                env_hints=list(row.get("env_hints") or []),
                note=str(row.get("note") or ""),
            )
        )
    return out


def _fetch_catalog_url(url: str) -> list[McpCatalogEntry]:
    cache_key = f"mcp_catalog_remote:{url}"
    cached = read_cache(cache_key, tenant_id="__global__")
    if isinstance(cached, list):
        return [
            McpCatalogEntry(**row) if isinstance(row, dict) else row
            for row in cached
            if isinstance(row, dict)
        ]

    if not is_safe_url(url):
        return []
    try:
        from butler.registry.url_safety import safe_registry_get

        resp = safe_registry_get(url)
        if resp.status_code != 200:
            return []
        text = resp.text
        if url.lower().endswith((".yaml", ".yml")):
            data = yaml.safe_load(text)
        else:
            data = resp.json()
    except Exception as exc:
        logger.debug("remote mcp catalog %s: %s", url, exc)
        return []

    entries = _parse_catalog_payload(data)
    write_cache(
        cache_key,
        [
            {
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "trust": e.trust,
                "transport": e.transport,
                "command": e.command,
                "args": e.args,
                "url": e.url,
                "env_hints": e.env_hints,
                "note": e.note,
            }
            for e in entries
        ],
        tenant_id="__global__",
    )
    return entries


def load_remote_catalog_entries() -> list[McpCatalogEntry]:
    if not remote_catalog_enabled():
        return []
    merged: list[McpCatalogEntry] = []
    seen: set[str] = set()
    for raw in os.getenv("BUTLER_MCP_CATALOG_URLS", "").split(","):
        url = raw.strip()
        if not url:
            continue
        for entry in _fetch_catalog_url(url):
            key = entry.id.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
    return merged
