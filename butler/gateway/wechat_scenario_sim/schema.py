from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SessionMode = Literal["shared", "fresh"]
Tier = Literal["fast", "standard", "slow"]


@dataclass(frozen=True)
class ScenarioCase:
    name: str
    user_text: str
    expect_reply_any: tuple[str, ...] = ()
    reject_reply_any: tuple[str, ...] = ()
    expect_tools_any: tuple[str, ...] = ()
    prefer_tools_any: tuple[str, ...] = ()
    forbid_tools: tuple[str, ...] = ()
    tier: Tier = "standard"
    max_seconds: float = 120.0
    requires_mcp: bool = False
    skip_in_quick: bool = False
    fresh_session: bool = False
    soft: bool = False
    verify_files_exist: tuple[str, ...] = ()
    verify_files_missing: tuple[str, ...] = ()
    verify_file_contains: tuple["FileContainsSpec", ...] = ()
    prompt_hint: str = ""
    require_tools: bool = False
    simulate_wechat_outbound: bool = False
    expect_outbound_any: tuple[str, ...] = ()
    min_outbound_messages: int = 0


@dataclass(frozen=True)
class FileContainsSpec:
    path: str
    substrings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioTrack:
    id: str
    title: str
    session_mode: SessionMode = "shared"
    quick: bool = True
    requires_mcp: bool = False
    setup: tuple[str, ...] = ()
    cleanup_globs: tuple[str, ...] = ()
    cases: tuple[ScenarioCase, ...] = ()
    simulate_wechat_outbound: bool = False


@dataclass(frozen=True)
class ScenarioManifest:
    title: str
    path: Path
    default_project: str = "灵文1号"
    verify_phrases: tuple[str, ...] = ()
    tracks: tuple[ScenarioTrack, ...] = ()


@dataclass
class ScenarioCaseResult:
    name: str
    track_id: str
    ok: bool
    reply_preview: str = ""
    tools: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""
    outbound_preview: str = ""
    outbound_count: int = 0


@dataclass
class ScenarioSimReport:
    ok: bool = True
    tracks_run: int = 0
    cases_run: int = 0
    cases_passed: int = 0
    cases_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cases: list[ScenarioCaseResult] = field(default_factory=list)
