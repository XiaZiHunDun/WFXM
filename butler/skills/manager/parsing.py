from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional

import yaml  # type: ignore[import-untyped]

from .constants import _FRONTMATTER_RE, MAX_DESC_LEN, MAX_NAME_LEN, VALID_NAME_RE
from .errors import _record_skill_load_error, SKILL_LOAD_ERR_ENCODING, SKILL_LOAD_ERR_IO, SKILL_LOAD_ERR_NO_FRONTMATTER, SKILL_LOAD_ERR_UNTERMINATED

logger = logging.getLogger(__name__)


def _validate_name(name: str) -> Optional[str]:
    if not name:
        return "Skill name is required."
    if len(name) > MAX_NAME_LEN:
        return f"Skill name exceeds {MAX_NAME_LEN} characters."
    if not VALID_NAME_RE.match(name):
        return (
            "Invalid skill name — use lowercase letters, digits, dots, hyphens, "
            "underscores; must start with a letter or digit."
        )
    return None


def _preferred_tools_from_fm(fm: dict[str, Any]) -> list[str]:
    pt = fm.get("preferred_tools") or []
    if isinstance(pt, str):
        return [pt.strip()] if pt.strip() else []
    if isinstance(pt, list):
        return [str(t).strip() for t in pt if str(t).strip()]
    return []


def _parse_skill_md(text: str, path: Path, source: str) -> Optional[dict[str, Any]]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        logger.warning(
            "Skill file missing or malformed YAML frontmatter (regex match failed): %s",
            path,
        )
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        logger.warning("Bad YAML frontmatter in %s: %s", path, e)
        return None
    if not isinstance(fm, dict):
        return None
    body = m.group(2).lstrip("\n")
    name = str(fm.get("name") or path.stem)
    triggers = fm.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [triggers]
    triggers = [str(t) for t in triggers]
    out: dict[str, Any] = {
        "name": name,
        "description": str(fm.get("description", "")),
        "triggers": triggers,
        "version": fm.get("version", 1),
        "created": str(fm.get("created", "")),
        "content": body,
        "_path": path,
        "_source": source,
    }
    pt = _preferred_tools_from_fm(fm)
    if pt:
        out["preferred_tools"] = pt
    return out


def _parse_skill_frontmatter(frontmatter: str, path: Path, source: str) -> Optional[dict[str, Any]]:
    try:
        fm = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as e:
        logger.warning("Bad YAML frontmatter in %s: %s", path, e)
        return None
    if not isinstance(fm, dict):
        return None
    name = str(fm.get("name") or path.stem)
    triggers = fm.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [triggers]
    triggers = [str(t) for t in triggers]
    out: dict[str, Any] = {
        "name": name,
        "description": str(fm.get("description", "")),
        "triggers": triggers,
        "version": fm.get("version", 1),
        "created": str(fm.get("created", "")),
        "_path": path,
        "_source": source,
    }
    if str(fm.get("install_type") or "") == "directory":
        out["install_type"] = "directory"
        out["content_path"] = str(fm.get("content_path") or "")
    pt = _preferred_tools_from_fm(fm)
    if pt:
        out["preferred_tools"] = pt
    return out


def _read_frontmatter_only(path: Path) -> Optional[str]:
    try:
        with path.open("rb") as f:
            first = f.readline()
            if first.strip() != b"---":
                msg = f"Skill file has no YAML frontmatter opener (---): {path}"
                logger.warning(msg)
                _record_skill_load_error(
                    SKILL_LOAD_ERR_NO_FRONTMATTER, path, msg
                )
                return None
            lines: list[bytes] = []
            for line in f:
                if line.strip() == b"---":
                    return b"".join(lines).decode("utf-8")
                lines.append(line)
    except UnicodeDecodeError as exc:
        msg = f"Skill file frontmatter has invalid UTF-8 encoding: {path}"
        logger.error(msg, exc_info=exc)
        _record_skill_load_error(SKILL_LOAD_ERR_ENCODING, path, msg)
        return None
    except OSError as exc:
        msg = f"Skill file could not be opened: {path}"
        logger.error(msg, exc_info=exc)
        _record_skill_load_error(SKILL_LOAD_ERR_IO, path, msg)
        return None

    msg = f"Skill file has unterminated YAML frontmatter (no closing ---): {path}"
    logger.warning(msg)
    _record_skill_load_error(SKILL_LOAD_ERR_UNTERMINATED, path, msg)
    return None


def _render_skill_md(skill: dict[str, Any]) -> str:
    fm = {
        "name": skill["name"],
        "description": skill["description"],
        "triggers": list(skill.get("triggers") or []),
        "version": int(skill.get("version", 1) or 1),
        "created": str(skill.get("created", date.today().isoformat())),
    }
    body = str(skill.get("content", skill.get("body", "")))
    fm_yaml = yaml.safe_dump(
        fm,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).strip()
    return f"---\n{fm_yaml}\n---\n{body}"