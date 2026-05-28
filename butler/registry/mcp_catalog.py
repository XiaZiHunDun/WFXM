"""MCP server catalog (curated templates)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from butler.registry.paths import catalog_dir, default_mcp_config_path, mcp_lock_path

logger = logging.getLogger(__name__)


@dataclass
class McpCatalogEntry:
    id: str
    title: str
    description: str
    trust: str = "trusted"
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    env_hints: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""


def mcp_catalog_enabled() -> bool:
    raw = os.getenv("BUTLER_MCP_CATALOG", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


_catalog_integrity_checked = False


def _ensure_catalog_integrity_once() -> None:
    global _catalog_integrity_checked
    if _catalog_integrity_checked:
        return
    _catalog_integrity_checked = True
    try:
        from butler.registry.catalog_integrity import ensure_catalog_integrity

        ensure_catalog_integrity()
    except Exception as exc:
        logger.warning("MCP catalog integrity: %s", exc)


class McpCatalogService:
    def _load_bundled_entries(self) -> list[McpCatalogEntry]:
        _ensure_catalog_integrity_once()
        path = catalog_dir() / "mcp" / "servers.yaml"
        if not path.is_file():
            return []
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("mcp catalog load: %s", exc)
            return []
        rows = data.get("servers") if isinstance(data, dict) else None
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
                    trust=str(row.get("trust") or "trusted"),
                    transport=str(row.get("transport") or "stdio"),
                    command=str(row.get("command") or ""),
                    args=[str(a) for a in (row.get("args") or [])],
                    url=str(row.get("url") or ""),
                    env_hints=list(row.get("env_hints") or []),
                    note=str(row.get("note") or ""),
                )
            )
        return out

    def _load_entries(self) -> list[McpCatalogEntry]:
        bundled = self._load_bundled_entries()
        seen = {e.id.lower() for e in bundled}
        out = list(bundled)
        try:
            from butler.registry.mcp_catalog_remote import load_remote_catalog_entries

            for entry in load_remote_catalog_entries():
                if entry.id.lower() in seen:
                    continue
                seen.add(entry.id.lower())
                out.append(entry)
        except Exception as exc:
            logger.debug("remote mcp catalog merge: %s", exc)
        return out

    def search(self, query: str, *, limit: int = 20) -> list[McpCatalogEntry]:
        q = query.strip().lower()
        hits = []
        for e in self._load_entries():
            if not q or q in e.id.lower() or q in e.title.lower() or q in e.description.lower():
                hits.append(e)
            if len(hits) >= limit:
                break
        return hits

    def get(self, server_id: str) -> McpCatalogEntry | None:
        sid = server_id.strip().lower()
        for e in self._load_entries():
            if e.id.lower() == sid:
                return e
        return None

    def list_installed_ids(self) -> list[str]:
        path = default_mcp_config_path()
        if not path.is_file():
            return []
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        block = data.get("servers") if isinstance(data, dict) else None
        if not isinstance(block, dict):
            return []
        return sorted(block.keys())

    def format_search(self, entries: list[McpCatalogEntry]) -> str:
        if not entries:
            return "无匹配 MCP 模板。"
        lines = ["MCP 目录:", ""]
        for e in entries:
            lines.append(f"• {e.id} — {e.title}\n  {e.description[:120]}")
        lines.append("\n安装: butler mcp add <id>  或  /mcp 安装 <id>")
        return "\n".join(lines)

    def format_inspect(self, entry: McpCatalogEntry) -> str:
        lines = [
            f"{entry.title} [{entry.trust}]",
            f"id: {entry.id}",
            f"transport: {entry.transport}",
            f"{entry.description[:400]}",
        ]
        if entry.transport == "stdio":
            lines.append(f"command: {entry.command} {' '.join(entry.args)}".strip())
        elif entry.url:
            lines.append(f"url: {entry.url}")
        if entry.env_hints:
            lines.append("环境变量:")
            for hint in entry.env_hints:
                name = str(hint.get("name") or "")
                req = "必填" if hint.get("required") else "可选"
                lines.append(f"  • {name} ({req})")
        if entry.note:
            lines.append(f"说明: {entry.note}")
        lines.append("\n安装: butler mcp add {0} --env KEY=VAL".format(entry.id))
        return "\n".join(lines)

    def load_lock_summary(self) -> dict[str, Any]:
        path = mcp_lock_path()
        if not path.is_file():
            return {}
        try:
            import json

            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
