"""Skill frontmatter lint (warn-only; does not block installs or runtime)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillLintIssue:
    skill_name: str
    code: str
    message: str


def lint_skill_summaries(summaries: list[dict[str, Any]]) -> list[SkillLintIssue]:
    """Warn when a routable skill lacks ``preferred_tools`` for execution pin."""
    issues: list[SkillLintIssue] = []
    for sk in summaries:
        name = str(sk.get("name") or "").strip()
        if not name:
            continue
        triggers = sk.get("triggers") or []
        preferred = sk.get("preferred_tools") or []
        if triggers and not preferred:
            issues.append(
                SkillLintIssue(
                    skill_name=name,
                    code="missing_preferred_tools",
                    message=(
                        f"Skill `{name}` 有 triggers 但缺 preferred_tools；"
                        "建议对齐常用 builtin 工具以便经验/注入时 pin。"
                    ),
                )
            )
    return issues


def format_lint_report(issues: list[SkillLintIssue]) -> str:
    if not issues:
        return "技能 lint：通过（无 warn）"
    lines = [f"技能 lint：{len(issues)} 条 warn"]
    for item in issues:
        lines.append(f"  • [{item.code}] {item.skill_name}: {item.message}")
    return "\n".join(lines)


__all__ = ["SkillLintIssue", "format_lint_report", "lint_skill_summaries"]
