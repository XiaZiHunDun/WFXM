"""Parse pinned DESIGN.md sections for post-compaction and system context (design-md subset)."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_SECTIONS = (
    "Overview",
    "Do's and Don'ts",
    "Responsive Behavior",
    "Colors",
    "Typography",
)


def default_section_names() -> tuple[str, ...]:
    raw = os.getenv("BUTLER_POST_COMPACT_DESIGN_SECTIONS", "").strip()
    if not raw:
        return _DEFAULT_SECTIONS
    parts = tuple(s.strip() for s in raw.split(",") if s.strip())
    return parts or _DEFAULT_SECTIONS


def max_section_chars() -> int:
    try:
        return int_env("BUTLER_POST_COMPACT_DESIGN_MAX_CHARS", 2500, min=200, max=8000)
    except ValueError:
        return 2500


def design_preset_dir() -> Path | None:
    raw = os.getenv("BUTLER_DESIGN_PRESET_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def resolve_design_md_path(
    workspace: Path,
    *,
    design_preset: str = "",
) -> Path | None:
    """Resolve DESIGN.md: workspace root, .butler/design/, optional preset slug."""
    ws = workspace.expanduser().resolve()
    candidates: list[Path] = [
        ws / "DESIGN.md",
        ws / ".butler" / "design" / "DESIGN.md",
    ]
    preset = str(design_preset or "").strip()
    if preset:
        slug = preset.replace("/", "").replace("\\", "").strip()
        if slug:
            candidates.append(ws / ".butler" / "design" / slug / "DESIGN.md")
            base = design_preset_dir()
            if base is not None:
                candidates.append((base / slug / "DESIGN.md").expanduser())
    for path in candidates:
        try:
            if path.is_file():
                return path.resolve()
        except OSError:
            continue
    return None


def _resolve_workspace() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        return Path(proj.workspace)
    except Exception:
        return None


def _current_design_preset() -> str:
    try:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return ""
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return ""
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return ""
        return str(getattr(proj, "design_preset", "") or "").strip()
    except Exception:
        return ""


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter dict, body without frontmatter)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    try:
        fm = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    body = text[end + 4 :].lstrip("\n")
    return fm, body


def format_frontmatter_summary(fm: dict[str, Any], *, max_chars: int = 600) -> str:
    if not fm:
        return ""
    lines: list[str] = []
    for key in ("name", "description", "brand", "version"):
        val = fm.get(key)
        if val is not None and str(val).strip():
            lines.append(f"- **{key}**: {str(val).strip()[:200]}")
    colors = fm.get("colors")
    if isinstance(colors, dict) and colors:
        sample = ", ".join(f"{k}={v}" for k, v in list(colors.items())[:6])
        lines.append(f"- **colors** (sample): {sample[:300]}")
    typo = fm.get("typography")
    if isinstance(typo, dict) and typo:
        sample = ", ".join(f"{k}={v}" for k, v in list(typo.items())[:4])
        lines.append(f"- **typography** (sample): {sample[:300]}")
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[:max_chars]
    if not block:
        return ""
    return "## DESIGN.md (frontmatter)\n" + block


def extract_design_md_sections(
    workspace: Path | None = None,
    *,
    section_names: tuple[str, ...] | None = None,
    design_preset: str = "",
) -> str:
    """Return markdown block of requested ## sections from project DESIGN.md."""
    ws = workspace or _resolve_workspace()
    if ws is None:
        return ""
    preset = design_preset or _current_design_preset()
    path = resolve_design_md_path(ws, design_preset=preset)
    if path is None:
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("DESIGN.md read failed: %s", exc)
        return ""

    fm, body = parse_frontmatter(raw)
    names = section_names or default_section_names()
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(body))
    sections: list[str] = []
    cap = max_section_chars()
    used = 0
    name_set = {n.lower() for n in names}

    summary = format_frontmatter_summary(fm, max_chars=min(500, cap // 3))
    if summary:
        sections.append(summary)
        used += len(summary)

    if not matches:
        if sections:
            rel = path.name
            return f"## DESIGN.md (pinned)\nSource: `{rel}`\n\n" + "\n\n".join(sections)
        return ""

    for i, match in enumerate(matches):
        title = match.group(1).strip()
        if title.lower() not in name_set:
            continue
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sect_body = body[start:end].strip()
        if not sect_body:
            continue
        block = f"## {title}\n{sect_body}"
        if used + len(block) > cap:
            block = block[: max(0, cap - used)]
        sections.append(block)
        used += len(block)
        if used >= cap:
            break

    if not sections:
        return ""
    rel = path.relative_to(ws) if path.is_relative_to(ws) else path.name
    header = f"## DESIGN.md (pinned sections)\nSource: `{rel}`\n\n"
    return header + "\n\n".join(sections)


def design_context_enabled() -> bool:
    from butler.env_parse import env_truthy, int_env

    return env_truthy("BUTLER_DESIGN_CONTEXT_INJECT", default=True)


def build_design_context_block(
    workspace: Path | None = None,
    *,
    design_preset: str = "",
) -> str:
    """Compact DESIGN excerpt for orchestrator memory (when file exists)."""
    if not design_context_enabled():
        return ""
    return extract_design_md_sections(
        workspace,
        section_names=default_section_names(),
        design_preset=design_preset,
    )


__all__ = [
    "build_design_context_block",
    "default_section_names",
    "design_context_enabled",
    "extract_design_md_sections",
    "format_frontmatter_summary",
    "parse_frontmatter",
    "resolve_design_md_path",
]
