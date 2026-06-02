"""Audit 6.1.1: README and several plan docs linked to the deleted
``project-assessment-2026-05.md`` and other dropped review files. The
replacement is the new ``project-deep-audit-2026-06.md``. No markdown link
in the repo should still point at a 2026-05 review filename that was removed
in the refactor."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DELETED_REVIEW_BASENAMES = (
    "project-assessment-2026-05.md",
    "project-deep-review-2026-05.md",
    "project-deep-review-2026-05-v2.md",
    "project-deep-review-round2-2026-05.md",
    "project-issue-tracker-2026-05.md",
    "project-multi-round-review-2026-05.md",
)
REPLACEMENT_BASENAME = "project-deep-audit-2026-06.md"

# Markdown link target pattern (no whitespace in URL)
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")


def _scan_markdown_links() -> list[tuple[Path, str]]:
    """Return (file, link_target) pairs where the link points at a deleted review doc."""
    hits: list[tuple[Path, str]] = []
    for path in REPO_ROOT.rglob("*.md"):
        if path.name == REPLACEMENT_BASENAME:
            # The replacement doc is allowed to mention the old names in audit text
            continue
        if ".git" in path.parts or "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in LINK_RE.finditer(text):
            target = match.group(1).split("#", 1)[0].split("?", 1)[0]
            base = target.rsplit("/", 1)[-1]
            if base in DELETED_REVIEW_BASENAMES:
                hits.append((path.relative_to(REPO_ROOT), target))
    return hits


def test_no_markdown_link_points_to_deleted_review_docs():
    """Audit 6.1.1: 7 broken links to project-assessment-2026-05.md etc.
    Fix: repoint to project-deep-audit-2026-06.md or remove."""
    hits = _scan_markdown_links()
    formatted = "\n".join(f"  {p}: {t}" for p, t in hits)
    assert not hits, (
        f"Found {len(hits)} broken markdown links to deleted 2026-05 review docs.\n"
        f"Update them to point at {REPLACEMENT_BASENAME} (or remove).\n{formatted}"
    )


def test_replacement_audit_doc_exists():
    assert (REPO_ROOT / "docs" / "reviews" / REPLACEMENT_BASENAME).is_file(), (
        f"replacement audit doc {REPLACEMENT_BASENAME} must exist"
    )


@pytest.mark.parametrize("basename", DELETED_REVIEW_BASENAMES)
def test_deleted_review_doc_actually_gone(tmp_path, basename):
    """Sanity: the link fix only makes sense if the old doc is actually deleted."""
    target = REPO_ROOT / "docs" / "reviews" / basename
    assert not target.exists(), (
        f"{basename} is unexpectedly back in the tree; re-check audit 6.1.1 context"
    )
