"""Skill registry service best-effort helpers (P0-A)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_types import SkillBundle, SkillSearchHit

logger = logging.getLogger(__name__)


def ensure_catalog_integrity_safe() -> None:
    def _run() -> None:
        from butler.registry.catalog_integrity import ensure_catalog_integrity

        ensure_catalog_integrity()

    safe_best_effort(_run, label="skill_service.catalog_integrity", default=None)


def search_source_safe(
    src: SkillSource,
    query: str,
    *,
    limit: int,
) -> list[SkillSearchHit]:
    def _run() -> list[SkillSearchHit]:
        return list(src.search(query, limit=limit))

    result = safe_best_effort(
        _run,
        label=f"skill_service.search.{src.source_id}",
        default=[],
    )
    return result if isinstance(result, list) else []


def inspect_source_safe(src: SkillSource, identifier: str) -> SkillSearchHit | None:
    def _run() -> SkillSearchHit | None:
        return src.inspect(identifier)

    result = safe_best_effort(
        _run,
        label=f"skill_service.inspect.{src.source_id}",
        default=None,
    )
    return result if isinstance(result, SkillSearchHit) else None


def fetch_from_source_safe(src: SkillSource, identifier: str) -> SkillBundle | None:
    def _run() -> SkillBundle | None:
        return src.fetch(identifier)

    result = safe_best_effort(
        _run,
        label=f"skill_service.fetch.{src.source_id}",
        default=None,
    )
    return result if isinstance(result, SkillBundle) else None


def run_pre_install_scan_safe(
    bundle: SkillBundle,
    hit: SkillSearchHit | None,
) -> None:
    try:
        from butler.registry.install_scan import (
            install_pre_scan_fail_closed,
            pre_install_scan_skill,
        )

        h = hashlib.sha256()
        for key in sorted(bundle.files.keys()):
            piece = bundle.files[key]
            h.update(key.encode("utf-8"))
            h.update(piece if isinstance(piece, bytes) else piece.encode("utf-8"))
        bundle_digest = h.hexdigest()[:16]
        expected = ""
        if hit is not None:
            expected = str((hit.extra or {}).get("content_hash") or "").strip()
        if not expected:
            expected = str(bundle.metadata.get("content_hash") or "").strip()
        scan = pre_install_scan_skill(
            bundle,
            source=str(hit.source if hit else bundle.source),
            expected_content_hash=expected,
            actual_content_hash=bundle_digest,
        )
        if not scan.ok_to_install and install_pre_scan_fail_closed():
            raise ValueError(
                f"Install blocked by pre-scan ({scan.verdict}): {', '.join(scan.issues)}"
            )
    except ValueError:
        raise
    except Exception as exc:
        logger.debug("Skill pre-install scan skipped: %s", exc)
