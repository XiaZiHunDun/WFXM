"""Data models for skill registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillSearchHit:
    name: str
    description: str
    source: str
    identifier: str
    trust: str = "community"
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillBundle:
    name: str
    files: dict[str, str | bytes]
    source: str
    identifier: str
    trust: str = "community"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InstalledSkillRecord:
    name: str
    source: str
    identifier: str
    version: str | None
    installed_at: str
    content_hash: str
    install_path: str
    scan_verdict: str
    trust: str = "community"
