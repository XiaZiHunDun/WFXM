#!/usr/bin/env python3
"""Update docs/plans/ paths after subdirectory restructure."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MOVES: dict[str, str] = {
    "roadmap-backlog-and-boundaries-2026-05.md": "decisions",
    "four-reports-out-of-scope-2026-05.md": "decisions",
    "five-reports-not-done-2026-05.md": "decisions",
    "four-reports-improvement-roadmap-2026-05.md": "roadmaps",
    "five-reports-improvement-roadmap-2026-05.md": "roadmaps",
    "external-agent-reports-improvement-roadmap-2026-05.md": "roadmaps",
    "post-consolidation-roadmap-2026-05.md": "active",
    "cc-butler-gap-analysis-2026-05.md": "active",
    "consolidation-2026-05.md": "archive",
    "consolidation-p3-implementation-2026-05.md": "archive",
    "memory-unification-implementation-2026-05.md": "archive",
    "health-report-refactor-2026-05.md": "archive",
    "wechat-steer-implementation-2026-05.md": "archive",
    "p3-deferred-deep-dive-2026-05.md": "archive",
    "reference-learning-plan-2026-05.md": "archive",
}

CORPUS_PREFIXES = ("corpus-", "dev-assistant-corpus-", "wechat-corpus-ops", "wechat-dev-conversation", "wechat-real-")


def subdir_for(name: str) -> str:
    if name in MOVES:
        return MOVES[name]
    if any(name.startswith(p) for p in CORPUS_PREFIXES):
        return "corpus"
    return "comparisons"


def repl_path(match: re.Match[str]) -> str:
    prefix, name = match.group(1), match.group(2)
    sub = subdir_for(name)
    return f"{prefix}plans/{sub}/{name}"


# docs/plans/foo.md or ](plans/foo.md — not already plans/sub/
PAT = re.compile(
    r"((?:\.\./)*docs/|\]\()(?:plans/)(?!(?:active|decisions|roadmaps|comparisons|corpus|archive)/)"
    r"([a-z0-9._-]+\.md)"
)


def fix_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    new = PAT.sub(repl_path, text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def fix_plans_subdir_relatives(path: Path) -> bool:
    subdirs = {"active", "decisions", "roadmaps", "comparisons", "corpus", "archive"}
    rel = path.relative_to(ROOT)
    if len(rel.parts) != 4 or rel.parts[0] != "docs" or rel.parts[1] != "plans":
        return False
    if rel.parts[2] not in subdirs:
        return False

    text = path.read_text(encoding="utf-8")
    new = text
    for d in ("architecture", "guides", "config", "ops", "design", "history", "reviews"):
        new = new.replace(f"](../{d}/", f"](../../{d}/")
        new = new.replace(f"](../{d}.md)", f"](../../{d}.md)")
    new = new.replace("](../DOCUMENTATION.md)", "](../../DOCUMENTATION.md)")
    for d in ("CONTRIBUTING.md", "tests/", "projects/", "scripts/", "STRUCTURE.md", "AGENTS.md"):
        new = new.replace(f"](../../{d}", f"](../../../{d}")
    new = new.replace("](../../README.md)", "](../../../README.md)")
    for name, sub in MOVES.items():
        new = re.sub(rf"\]\(({re.escape(name)})\)", rf"](../{sub}/\1)", new)
        new = re.sub(rf"\]\(({re.escape(name)}#)", rf"](../{sub}/\1#", new)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


REL_PLANS = re.compile(r"\]\(\.\./plans/([a-z0-9._-]+\.md)")


def fix_relative_plans_links(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")

    def sub_rel(m: re.Match[str]) -> str:
        name = m.group(1)
        return f"](../plans/{subdir_for(name)}/{name}"

    new = REL_PLANS.sub(sub_rel, text)
    new = re.sub(
        r"\]\(plans/([a-z0-9._-]+\.md)",
        lambda m: f"](plans/{subdir_for(m.group(1))}/{m.group(1)}",
        new,
    )
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = 0
    skip_dirs = {".git", "node_modules", "reference", "projects"}
    for ext in ("*.md", "*.mdc", "*.yml", "*.yaml", "*.sh"):
        for path in ROOT.rglob(ext):
            if any(p in skip_dirs for p in path.parts):
                continue
            c1 = fix_file(path)
            c2 = fix_plans_subdir_relatives(path)
            c3 = fix_relative_plans_links(path)
            if c1 or c2 or c3:
                changed += 1
                print(path.relative_to(ROOT))
    print(f"updated {changed} files")


if __name__ == "__main__":
    main()
