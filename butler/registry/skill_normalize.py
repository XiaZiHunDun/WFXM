"""Normalize SkillBundle to Butler flat or directory skill layout."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import yaml

_VALID_NAME = re.compile(r"^[a-z][a-z0-9._-]*$")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
_SKILL_MD_NAMES = ("SKILL.md", "skill.md")
_ALLOWED_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml")


def validate_skill_name(name: str) -> str:
    key = str(name or "").strip().lower()
    if not key or not _VALID_NAME.match(key):
        raise ValueError(
            "Invalid skill name — use lowercase letters, digits, dots, hyphens, "
            "underscores; must start with a letter or digit."
        )
    return key[:64]


@dataclass(frozen=True)
class SkillInstallLayout:
    """Target layout under tenant skills root."""

    name: str
    kind: str  # flat | directory
    stub_md: str
    directory_files: dict[str, str]  # rel paths under skills/<name>/


def _find_skill_md_key(files: dict[str, str | bytes]) -> str | None:
    for key in _SKILL_MD_NAMES:
        if key in files:
            return key
    for key, val in files.items():
        if key.endswith(".md") and isinstance(val, (str, bytes)):
            return key
    return None


def _decode_file(content: str | bytes) -> str:
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = _FRONTMATTER.match(text)
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
        body = m.group(2).lstrip("\n")
        return fm, body
    return {}, text


def _normalize_frontmatter(fm: dict[str, Any], *, name: str) -> dict[str, Any]:
    out = dict(fm)
    out["name"] = validate_skill_name(str(out.get("name") or name))
    out.setdefault("description", str(out.get("description") or "")[:1024])
    out.setdefault("version", int(out.get("version") or 1))
    out.setdefault("created", str(out.get("created") or date.today().isoformat()))
    return out


def _is_directory_bundle(files: dict[str, str | bytes]) -> bool:
    skill_key = _find_skill_md_key(files)
    if skill_key is None:
        return False
    extra = [
        k
        for k in files
        if k != skill_key and _safe_rel_path(k) and k.lower().endswith(_ALLOWED_SUFFIXES)
    ]
    return len(extra) > 0


_DRIVE_LETTER_SEGMENT = re.compile(r"^[a-zA-Z]:")


def _safe_rel_path(rel: str) -> str | None:
    # Sprint 22-6 TEST-21-C-3: reject absolute paths and Windows drive
    # letters BEFORE lstrip mangles them. `c:/evil.md` (drive letter)
    # would otherwise pass and let a directory-bundle install escape
    # <skills_root>/<name>/. POSIX absolute paths are rejected up front
    # because lstrip("/") silently downgrades them to relative.
    if not isinstance(rel, str) or rel.startswith("/"):
        return None
    normalized = rel.replace("\\", "/").lstrip("/")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if not parts or ".." in parts:
        return None
    for part in parts:
        if _DRIVE_LETTER_SEGMENT.match(part):
            return None
    return "/".join(parts)


def bundle_install_layout(
    bundle_name: str,
    files: dict[str, str | bytes],
) -> SkillInstallLayout:
    """Plan install: single flat .md or directory + stub (REG-P2)."""
    decoded = {k: _decode_file(v) for k, v in files.items()}
    skill_key = _find_skill_md_key(decoded)
    if skill_key is None:
        raise ValueError("Bundle has no .md skill file")

    skill_text = decoded[skill_key]
    fm, body = _parse_frontmatter(skill_text)
    name = validate_skill_name(str(fm.get("name") or bundle_name))
    fm = _normalize_frontmatter(fm, name=name)

    if not _is_directory_bundle(files):
        fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
        return SkillInstallLayout(
            name=name,
            kind="flat",
            stub_md=f"---\n{fm_yaml}\n---\n{body}",
            directory_files={},
        )

    dir_files: dict[str, str] = {}
    skill_rel = _safe_rel_path(skill_key) or "SKILL.md"
    dir_files[skill_rel] = skill_text
    for rel, content in decoded.items():
        if rel == skill_key:
            continue
        safe = _safe_rel_path(rel)
        if not safe or not safe.lower().endswith(_ALLOWED_SUFFIXES):
            continue
        dir_files[safe] = content

    content_path = f"{name}/{skill_rel}"
    stub_fm = dict(fm)
    stub_fm["install_type"] = "directory"
    stub_fm["content_path"] = content_path
    stub_body = (
        f"Registry-installed directory skill. Content: `{content_path}`.\n"
        f"Attachments: {len(dir_files) - 1} file(s).\n"
    )
    stub_yaml = yaml.safe_dump(stub_fm, allow_unicode=True, sort_keys=False).strip()
    return SkillInstallLayout(
        name=name,
        kind="directory",
        stub_md=f"---\n{stub_yaml}\n---\n{stub_body}",
        directory_files=dir_files,
    )


def bundle_to_markdown(bundle_name: str, files: dict[str, str | bytes]) -> tuple[str, str]:
    """Return (skill_name, full_md_content) for flat-only callers."""
    layout = bundle_install_layout(bundle_name, files)
    if layout.kind != "flat":
        raise ValueError("Bundle is multi-file; use bundle_install_layout()")
    return layout.name, layout.stub_md
