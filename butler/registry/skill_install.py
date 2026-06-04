"""Quarantine, scan, and install skill bundles."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from butler.registry.audit import append_audit
from butler.registry.paths import quarantine_dir, skills_root
from butler.registry.skill_lock import SkillLockFile
from butler.registry.skill_normalize import (
    bundle_install_layout,
    validate_skill_name,
)
from butler.registry.skill_types import InstalledSkillRecord, SkillBundle
from butler.skills.guard import scan_skill_text

logger = logging.getLogger(__name__)


def _max_bytes() -> int:
    try:
        mb = float(os.getenv("BUTLER_SKILL_INSTALL_MAX_MB", "2"))
        return int(mb * 1024 * 1024)
    except ValueError:
        return 2 * 1024 * 1024


def content_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def quarantine_bundle(bundle: SkillBundle, *, tenant_id: str = "") -> Path:
    name = validate_skill_name(bundle.name)
    dest = quarantine_dir(tenant_id=tenant_id) / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    total = 0
    for rel, content in bundle.files.items():
        safe = rel.replace("\\", "/").lstrip("/")
        if ".." in safe.split("/"):
            raise ValueError(f"Unsafe path in bundle: {rel}")
        if not safe.endswith((".md", ".txt", ".json")):
            continue
        piece = content if isinstance(content, bytes) else content.encode("utf-8")
        total += len(piece)
        if total > _max_bytes():
            raise ValueError(f"Skill bundle exceeds {_max_bytes()} bytes")
        target = dest / safe
        resolved = target.resolve()
        if not str(resolved).startswith(str(dest.resolve())):
            raise ValueError(f"Unsafe path escapes quarantine: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    return dest


def scan_quarantine(path: Path) -> tuple[str, list[str]]:
    issues: list[str] = []
    for f in path.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".md", ".txt"):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                issues.append("unreadable")
                continue
            issues.extend(scan_skill_text(text))
    verdict = "clean" if not issues else "warn"
    if any(x in issues for x in ("prompt_injection", "code_eval", "shell_exec", "subprocess")):
        verdict = "block"
    return verdict, sorted(set(issues))


def install_from_quarantine(
    qpath: Path,
    bundle: SkillBundle,
    *,
    tenant_id: str = "",
    name_override: str = "",
) -> InstalledSkillRecord:
    decoded = {
        k: (v.decode("utf-8", errors="replace") if isinstance(v, bytes) else v)
        for k, v in bundle.files.items()
    }
    layout = bundle_install_layout(name_override or bundle.name, decoded)
    if name_override:
        layout_name = validate_skill_name(name_override)
    else:
        layout_name = layout.name

    verdict, _issues = scan_quarantine(qpath)
    if verdict == "block":
        raise ValueError("Skill blocked by security scan")

    root = skills_root(tenant_id=tenant_id)
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{layout_name}.md"
    dest.write_text(layout.stub_md, encoding="utf-8")

    if layout.kind == "directory" and layout.directory_files:
        skill_dir = root / layout_name
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)
        skill_dir.mkdir(parents=True, exist_ok=True)
        for rel, text in layout.directory_files.items():
            safe = rel.replace("\\", "/").lstrip("/")
            if ".." in safe.split("/"):
                continue
            target = skill_dir / safe
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")

    from butler.skills.guard import validate_skill_install

    validate_skill_install(dest)
    if layout.kind == "directory":
        content_rel = _content_path_from_stub(layout.stub_md)
        if content_rel:
            content_file = root / content_rel
            if content_file.is_file():
                validate_skill_install(content_file)

    if qpath.exists():
        shutil.rmtree(qpath, ignore_errors=True)

    record = InstalledSkillRecord(
        name=layout_name,
        source=bundle.source,
        identifier=bundle.identifier,
        version=str((bundle.metadata or {}).get("version") or "") or None,
        installed_at=datetime.now(timezone.utc).isoformat(),
        content_hash=content_hash(dest),
        install_path=f"{layout_name}.md",
        scan_verdict=verdict,
        trust=bundle.trust,
    )
    SkillLockFile(tenant_id=tenant_id).record_install(record)
    append_audit("SKILL_INSTALL", layout_name, f"{bundle.source}:{bundle.identifier}")
    return record


def _content_path_from_stub(stub_md: str) -> str:
    import re as _re

    import yaml as _yaml

    m = _re.match(r"\A---\s*\n(.*?)\n---", stub_md, _re.DOTALL)
    if not m:
        return ""
    try:
        fm = _yaml.safe_load(m.group(1)) or {}
    except _yaml.YAMLError:
        return ""
    if isinstance(fm, dict) and str(fm.get("install_type") or "") == "directory":
        return str(fm.get("content_path") or "").strip()
    return ""


def uninstall_skill(name: str, *, tenant_id: str = "") -> tuple[bool, str]:
    lock = SkillLockFile(tenant_id=tenant_id)
    rec = lock.get(name)
    if not rec:
        return False, f"Skill '{name}' was not installed via registry (no lock entry)."
    root = skills_root(tenant_id=tenant_id)
    path = root / rec.install_path
    if path.is_file():
        try:
            stub = path.read_text(encoding="utf-8")
        except OSError:
            stub = ""
        content_rel = _content_path_from_stub(stub)
        path.unlink()
        if content_rel:
            content_file = root / content_rel
            # Sprint 19-2 SEC-19-A-3: 防 path traversal, content_file.resolve() 必须
            # 在 root.resolve() 内. 恶意 frontmatter (e.g. `../../../tmp/important`)
            # 会让 rmtree 删除 root 外任意目录, fail-closed 拒绝卸载.
            root_resolved = root.resolve()
            content_resolved = (root / content_rel).resolve()
            if not str(content_resolved).startswith(str(root_resolved) + os.sep):
                return False, (
                    f"Skill '{name}' has unsafe content_path; "
                    f"refusing to uninstall to prevent path traversal"
                )
            if content_file.is_file():
                skill_dir = content_file.parent
                if skill_dir.is_dir() and skill_dir != root:
                    shutil.rmtree(skill_dir, ignore_errors=True)
    skill_dir = root / name
    if skill_dir.is_dir():
        shutil.rmtree(skill_dir, ignore_errors=True)
    lock.remove(name)
    append_audit("SKILL_UNINSTALL", name, rec.identifier)
    return True, f"Uninstalled skill '{name}'."
