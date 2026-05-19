"""Static security scan for Butler skill files (simplified skills_guard)."""

from __future__ import annotations

import re
from pathlib import Path

DANGEROUS_PATTERNS = [
    (re.compile(r"ignore\s+previous\s+instructions", re.I), "prompt_injection"),
    (re.compile(r"you\s+are\s+now\s+", re.I), "role_override"),
    (re.compile(r"<\s*script\b", re.I), "html_script"),
    (re.compile(r"eval\s*\(", re.I), "code_eval"),
    (re.compile(r"os\.system\s*\(", re.I), "shell_exec"),
    (re.compile(r"subprocess\.", re.I), "subprocess"),
    (re.compile(r"__import__\s*\(", re.I), "dynamic_import"),
]


def scan_skill_text(text: str) -> list[str]:
    """Return list of issue codes found in skill content."""
    issues: list[str] = []
    for pattern, code in DANGEROUS_PATTERNS:
        if pattern.search(text):
            issues.append(code)
    return issues


def scan_skill_file(path: Path) -> tuple[bool, list[str]]:
    """Return (is_safe, issue_codes)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False, ["unreadable"]
    issues = scan_skill_text(text)
    return len(issues) == 0, issues


def validate_skill_install(path: Path) -> None:
    """Raise ValueError if skill file fails guard scan."""
    safe, issues = scan_skill_file(path)
    if not safe:
        raise ValueError(f"Skill failed security scan: {', '.join(issues)}")
