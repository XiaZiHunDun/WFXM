"""Claude marketplace compatibility cards and install follow-up hints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from butler.registry.skill_sources.marketplace import (
    _catalog_entries,
    _marketplace_json_for,
    _parse_identifier,
)


def _load_mcp_server_ids() -> set[str]:
    from butler.registry.marketplace_compat_ops import load_mcp_server_ids_safe

    return load_mcp_server_ids_safe()


def marketplace_document(mp_id: str) -> dict[str, Any] | None:
    for catalog in _catalog_entries():
        if catalog.id != mp_id:
            continue
        data = _marketplace_json_for(catalog)
        return data if isinstance(data, dict) else None
    return None


def get_compatibility(mp_id: str) -> dict[str, Any] | None:
    data = marketplace_document(mp_id)
    if not data:
        return None
    compat = data.get("compatibility")
    return compat if isinstance(compat, dict) else None


def format_adoption_lines(compat: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    plugin = str(compat.get("claude_plugin") or compat.get("plugin") or "").strip()
    if plugin:
        lines.append(f"plugin:{plugin}")
    adopted = compat.get("adopted") if isinstance(compat.get("adopted"), dict) else {}
    for key in ("skills", "mcp", "l2"):
        vals = adopted.get(key)
        if isinstance(vals, list) and vals:
            lines.append(f"adopted:{key}=" + ",".join(str(v) for v in vals))
    not_adopted = compat.get("not_adopted")
    if isinstance(not_adopted, list) and not_adopted:
        lines.append("not_adopted=" + ",".join(str(x) for x in not_adopted[:4]))
    return lines


def install_followup_lines(identifier: str) -> list[str]:
    """Post-install hints: suggested MCP and not-adopted components."""
    parsed = _parse_identifier(identifier)
    if not parsed:
        return []
    mp_id, _plugin = parsed
    compat = get_compatibility(mp_id)
    if not compat:
        return []
    lines: list[str] = []
    adopted = compat.get("adopted") if isinstance(compat.get("adopted"), dict) else {}
    suggested = compat.get("mcp_suggested")
    if not isinstance(suggested, list):
        suggested = adopted.get("mcp") if isinstance(adopted.get("mcp"), list) else []
    configured = _load_mcp_server_ids()
    for row in suggested:
        sid = ""
        reason = ""
        if isinstance(row, str):
            sid = row.strip()
        elif isinstance(row, dict):
            sid = str(row.get("id") or row.get("name") or "").strip()
            reason = str(row.get("reason") or "").strip()
        if not sid:
            continue
        if sid in configured:
            continue
        hint = f"建议配置 MCP [{sid}]"
        if reason:
            hint += f"（{reason}）"
        hint += f"：butler mcp add {sid} 或微信 /mcp 安装 {sid}"
        lines.append(hint)
    not_adopted = compat.get("not_adopted")
    if isinstance(not_adopted, list) and not_adopted:
        sample = "、".join(str(x) for x in not_adopted[:3])
        lines.append(f"未接入 Claude 组件：{sample}（见 stack plugin_adoption）")
    return lines


def format_install_followup(identifier: str) -> str:
    lines = install_followup_lines(identifier)
    if not lines:
        return ""
    return "\n".join(lines)


def check_directory_skill_layout(
    name: str,
    *,
    workspace: Path,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    """Return (ok, detail) for directory-layout skills (stub + content tree)."""
    skill_name = str(name).strip()
    if not skill_name:
        return False, "empty"
    candidates: list[Path] = []
    proj_stub = workspace / ".butler" / "skills" / f"{skill_name}.md"
    if proj_stub.is_file():
        candidates.append(proj_stub)
    from butler.registry.marketplace_compat_ops import tenant_skill_stub_path_safe

    tenant_stub = tenant_skill_stub_path_safe(tenant_id=tenant_id, skill_name=skill_name)
    if tenant_stub is not None:
        candidates.append(tenant_stub)
    if not candidates:
        return False, "missing"
    stub = candidates[0]
    try:
        text = stub.read_text(encoding="utf-8")
    except OSError:
        return False, "unreadable"
    import re as _re

    m = _re.match(r"\A---\s*\n(.*?)\n---", text, _re.DOTALL)
    if not m:
        return False, "flat"
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict) or str(fm.get("install_type") or "") != "directory":
        return False, "flat"
    content_rel = str(fm.get("content_path") or "").strip()
    if not content_rel:
        return False, "no_content_path"
    root = stub.parent
    content_file = (root / content_rel).resolve()
    if not content_file.is_file():
        return False, "content_missing"
    skill_dir = content_file.parent
    ref_dir = skill_dir / "references"
    ref_count = sum(1 for p in ref_dir.rglob("*") if p.is_file()) if ref_dir.is_dir() else 0
    if ref_count == 0:
        return False, "no_references"
    return True, f"refs={ref_count}"


def missing_mcp_suggestions(compat: dict[str, Any]) -> list[str]:
    """Return warning lines for suggested MCP not present in mcp.yaml."""
    suggested = compat.get("mcp_suggested")
    if not isinstance(suggested, list):
        adopted = compat.get("adopted")
        if isinstance(adopted, dict):
            suggested = adopted.get("mcp")
    if not isinstance(suggested, list):
        return []
    configured = _load_mcp_server_ids()
    warnings: list[str] = []
    for row in suggested:
        sid = row if isinstance(row, str) else str((row or {}).get("id") or "")
        sid = sid.strip()
        if sid and sid not in configured:
            warnings.append(f"建议 MCP [{sid}] 未配置（butler mcp add {sid}）")
    return warnings


__all__ = [
    "check_directory_skill_layout",
    "format_adoption_lines",
    "format_install_followup",
    "get_compatibility",
    "install_followup_lines",
    "marketplace_document",
    "missing_mcp_suggestions",
]
