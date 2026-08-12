from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from .schema import FileContainsSpec, ScenarioCase, ScenarioManifest, ScenarioTrack


def _simulation_roots(workspace: Path | str | None = None) -> list[Path]:
    ws = Path(workspace or Path.cwd()).expanduser().resolve()
    roots: list[Path] = []
    for base in (ws / ".butler" / "simulation", Path.home() / ".butler" / "simulation"):
        if base.is_dir() and base not in roots:
            roots.append(base)
    return roots


def _parse_file_contains(raw: Any) -> tuple[FileContainsSpec, ...]:
    if not raw:
        return ()
    specs: list[FileContainsSpec] = []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return ()
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        any_raw = item.get("any") or item.get("substrings") or item.get("contains") or []
        if isinstance(any_raw, str):
            needles: tuple[str, ...] = (any_raw,)
        else:
            needles = tuple(str(x) for x in any_raw if str(x).strip())
        specs.append(FileContainsSpec(path=path, substrings=needles))
    return tuple(specs)


def _parse_case(raw: dict[str, Any]) -> ScenarioCase:
    def _tup(key: str) -> tuple[str, ...]:
        val = raw.get(key) or []
        if isinstance(val, str):
            return (val,)
        return tuple(str(x) for x in val)

    tier = str(raw.get("tier") or "standard").strip().lower()
    if tier not in ("fast", "standard", "slow"):
        tier = "standard"
    return ScenarioCase(
        name=str(raw.get("name") or "unnamed"),
        user_text=str(raw.get("user_text") or ""),
        expect_reply_any=_tup("expect_reply_any"),
        reject_reply_any=_tup("reject_reply_any"),
        expect_tools_any=_tup("expect_tools_any"),
        prefer_tools_any=_tup("prefer_tools_any"),
        forbid_tools=_tup("forbid_tools"),
        tier=tier,  # type: ignore[arg-type]
        max_seconds=float(raw.get("max_seconds") or 120.0),
        requires_mcp=bool(raw.get("requires_mcp")),
        skip_in_quick=bool(raw.get("skip_in_quick")),
        fresh_session=bool(raw.get("fresh_session")),
        soft=bool(raw.get("soft")),
        verify_files_exist=_tup("verify_files_exist"),
        verify_files_missing=_tup("verify_files_missing"),
        verify_file_contains=_parse_file_contains(raw.get("verify_file_contains")),
        prompt_hint=str(raw.get("prompt_hint") or "").strip(),
        require_tools=bool(raw.get("require_tools")),
        simulate_wechat_outbound=bool(raw.get("simulate_wechat_outbound")),
        expect_outbound_any=_tup("expect_outbound_any"),
        min_outbound_messages=int(raw.get("min_outbound_messages") or 0),
    )


def _parse_track(raw: dict[str, Any]) -> ScenarioTrack:
    setup_raw = raw.get("setup") or []
    if isinstance(setup_raw, str):
        setup: tuple[str, ...] = (setup_raw,)
    else:
        setup = tuple(str(x) for x in setup_raw)
    cleanup_raw = raw.get("cleanup_globs") or []
    if isinstance(cleanup_raw, str):
        cleanup_globs: tuple[str, ...] = (cleanup_raw,)
    else:
        cleanup_globs = tuple(str(x) for x in cleanup_raw)
    mode = str(raw.get("session_mode") or "shared").strip().lower()
    if mode not in ("shared", "fresh"):
        mode = "shared"
    cases = tuple(_parse_case(c) for c in (raw.get("cases") or []) if isinstance(c, dict))
    return ScenarioTrack(
        id=str(raw.get("id") or "track"),
        title=str(raw.get("title") or ""),
        session_mode=mode,  # type: ignore[arg-type]
        quick=bool(raw.get("quick", True)),
        requires_mcp=bool(raw.get("requires_mcp")),
        setup=setup,
        cleanup_globs=cleanup_globs,
        cases=cases,
        simulate_wechat_outbound=bool(raw.get("simulate_wechat_outbound")),
    )


def load_wechat_scenario_manifest(
    *,
    workspace: Path | str | None = None,
    filename: str = "wechat-owner-scenarios.yaml",
) -> ScenarioManifest | None:
    for root in _simulation_roots(workspace):
        path = root / filename
        if not path.is_file():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        tracks = tuple(
            _parse_track(t) for t in (data.get("tracks") or []) if isinstance(t, dict)
        )
        phrases = data.get("verify_phrases") or []
        return ScenarioManifest(
            title=str(data.get("title") or "WeChat Owner Scenario Sim"),
            path=path,
            default_project=str(data.get("default_project") or "灵文1号"),
            verify_phrases=tuple(str(p) for p in phrases),
            tracks=tracks,
        )
    return None
