"""Bundled registry catalog SHA-256 verification (Langflow component hash subset)."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from butler.env_parse import env_truthy
from butler.registry.paths import catalog_dir

logger = logging.getLogger(__name__)

_MANIFEST_NAME = "manifest.sha256"


def catalog_integrity_enabled() -> bool:
    return bool(env_truthy("BUTLER_CATALOG_INTEGRITY", default=True))


def _manifest_path() -> Path:
    return Path(catalog_dir()) / _MANIFEST_NAME


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(*, root: Path | None = None) -> dict[str, str]:
    base = root or catalog_dir()
    out: dict[str, str] = {}
    if not base.is_dir():
        return out
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        if path.name == _MANIFEST_NAME:
            continue
        rel = path.relative_to(base).as_posix()
        out[rel] = _sha256_file(path)
    return out


def write_manifest(*, root: Path | None = None) -> Path:
    base = root or catalog_dir()
    data = build_manifest(root=base)
    path = base / _MANIFEST_NAME
    lines = [f"{digest}  {rel}\n" for rel, digest in sorted(data.items())]
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _parse_manifest(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, rel = parts[0].strip(), parts[1].strip()
        if len(digest) == 64:
            out[rel] = digest
    return out


def verify_catalog_integrity(*, root: Path | None = None) -> tuple[bool, list[str]]:
    """Return (ok, errors)."""
    if not catalog_integrity_enabled():
        return True, []
    base = root or catalog_dir()
    manifest = base / _MANIFEST_NAME
    if not manifest.is_file():
        return True, ["manifest missing (skip)"]

    expected = _parse_manifest(manifest.read_text(encoding="utf-8"))
    if not expected:
        return True, []

    errors: list[str] = []
    for rel, want in expected.items():
        path = base / rel
        if not path.is_file():
            errors.append(f"missing: {rel}")
            continue
        got = _sha256_file(path)
        if got != want:
            errors.append(f"hash mismatch: {rel}")
    return len(errors) == 0, errors


def ensure_catalog_integrity() -> None:
    ok, errors = verify_catalog_integrity()
    if ok:
        return
    if os.getenv("BUTLER_CATALOG_INTEGRITY_FAIL_CLOSED", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        logger.warning("Catalog integrity warnings: %s", errors[:5])
        return
    raise RuntimeError(
        "Bundled catalog integrity check failed: "
        + "; ".join(errors[:8])
        + (" …" if len(errors) > 8 else "")
    )
