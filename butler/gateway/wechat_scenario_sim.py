"""WeChat owner scenario simulation via ButlerMessageHandler (no iLink).

Manifest SSOT: ``.butler/simulation/wechat-owner-scenarios.yaml``
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

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


@dataclass(frozen=True)
class SimRenderContext:
    """Per-run placeholders for manifest templates."""

    sim_date: str
    sim_id: str

    @property
    def sim_smoke_file(self) -> str:
        return f"owner-sim-smoke-{self.sim_date}.md"

    def render(self, text: str) -> str:
        if not text:
            return text
        return (
            text.replace("{sim_smoke_file}", self.sim_smoke_file)
            .replace("{sim_date}", self.sim_date)
            .replace("{sim_id}", self.sim_id)
        )

    def render_tuple(self, items: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self.render(x) for x in items)


def make_sim_render_context(*, today: date | None = None, run_ns: int | None = None) -> SimRenderContext:
    day = today or date.today()
    ns = run_ns if run_ns is not None else time.time_ns()
    return SimRenderContext(
        sim_date=day.isoformat(),
        sim_id=format(ns % 0xFFFFFF, "06x"),
    )


def render_scenario_case(case: ScenarioCase, ctx: SimRenderContext) -> ScenarioCase:
    return ScenarioCase(
        name=case.name,
        user_text=ctx.render(case.user_text),
        expect_reply_any=ctx.render_tuple(case.expect_reply_any),
        reject_reply_any=ctx.render_tuple(case.reject_reply_any),
        expect_tools_any=case.expect_tools_any,
        prefer_tools_any=case.prefer_tools_any,
        forbid_tools=case.forbid_tools,
        tier=case.tier,
        max_seconds=case.max_seconds,
        requires_mcp=case.requires_mcp,
        skip_in_quick=case.skip_in_quick,
        fresh_session=case.fresh_session,
        soft=case.soft,
        verify_files_exist=ctx.render_tuple(case.verify_files_exist),
        verify_files_missing=ctx.render_tuple(case.verify_files_missing),
    )


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


def _simulation_roots(workspace: Path | str | None = None) -> list[Path]:
    ws = Path(workspace or Path.cwd()).expanduser().resolve()
    roots: list[Path] = []
    for base in (ws / ".butler" / "simulation", Path.home() / ".butler" / "simulation"):
        if base.is_dir() and base not in roots:
            roots.append(base)
    return roots


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
    )


def _parse_track(raw: dict[str, Any]) -> ScenarioTrack:
    setup_raw = raw.get("setup") or []
    if isinstance(setup_raw, str):
        setup = (setup_raw,)
    else:
        setup = tuple(str(x) for x in setup_raw)
    cleanup_raw = raw.get("cleanup_globs") or []
    if isinstance(cleanup_raw, str):
        cleanup_globs = (cleanup_raw,)
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


def evaluate_scenario_case(
    tools: list[str],
    reply: str,
    case: ScenarioCase,
    *,
    strict: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for bad in case.reject_reply_any:
        if bad in reply:
            errors.append(f"reply must not contain {bad!r}")
    for tool in case.forbid_tools:
        if tool in tools:
            errors.append(f"forbidden tool {tool}")
    if case.expect_reply_any:
        if not any(needle in reply for needle in case.expect_reply_any):
            msg = f"reply missing any of {case.expect_reply_any}"
            if case.soft:
                warnings.append(msg)
            else:
                errors.append(msg)
    if case.expect_tools_any and not any(t in tools for t in case.expect_tools_any):
        msg = f"expected tools any of {case.expect_tools_any}, got {tools}"
        if strict and not case.soft:
            errors.append(msg)
        else:
            warnings.append(msg)
    if case.prefer_tools_any and not any(t in tools for t in case.prefer_tools_any):
        direct_ok = bool(case.expect_reply_any) and any(x in reply for x in case.expect_reply_any)
        msg = f"preferred tools {case.prefer_tools_any}, got {tools}"
        if strict and not direct_ok and not case.soft:
            errors.append(msg)
        else:
            warnings.append(msg)
    return errors, warnings


def _mcp_enabled() -> bool:
    return os.getenv("BUTLER_MCP_ENABLED", "0").strip() == "1"


def _has_llm_key() -> bool:
    return any(
        os.getenv(k, "").strip()
        for k in (
            "MINIMAX_API_KEY",
            "MINIMAX_CN_API_KEY",
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
        )
    )


def _project_workspace(session_key: str) -> Path | None:
    from butler.project.manager import ProjectManager

    proj = ProjectManager().get_current(session_key=session_key)
    if proj is None:
        return None
    return Path(proj.workspace)


def _verify_files_on_disk(
    case: ScenarioCase,
    session_key: str,
) -> list[str]:
    errors: list[str] = []
    if not case.verify_files_exist and not case.verify_files_missing:
        return errors
    ws = _project_workspace(session_key)
    if ws is None:
        return ["no current project workspace for file verify"]
    for rel in case.verify_files_exist:
        path = (ws / rel).resolve()
        if not path.is_file():
            errors.append(f"file missing on disk: {rel}")
    for rel in case.verify_files_missing:
        path = (ws / rel).resolve()
        if path.exists():
            errors.append(f"file should not exist: {rel}")
    return errors


def _cleanup_track_artifacts(
    track: ScenarioTrack,
    session_key: str,
    ctx: SimRenderContext,
) -> list[str]:
    if not track.cleanup_globs:
        return []
    ws = _project_workspace(session_key)
    if ws is None:
        return ["no workspace for cleanup_globs"]
    removed: list[str] = []
    for pattern in ctx.render_tuple(track.cleanup_globs):
        for path in sorted(ws.glob(pattern)):
            if path.is_file():
                path.unlink()
                removed.append(str(path.relative_to(ws)))
    return removed


def run_scenario_track(
    track: ScenarioTrack,
    handler: Any,
    *,
    owner_id: str,
    strict: bool = False,
    quick: bool = False,
    session_ns: int | None = None,
    render_ctx: SimRenderContext | None = None,
) -> list[ScenarioCaseResult]:
    from butler.core.session_epoch import load_current_turn_tool_actions

    if track.requires_mcp and not _mcp_enabled():
        return [
            ScenarioCaseResult(
                name="(track)",
                track_id=track.id,
                ok=True,
                skipped=True,
                skip_reason="BUTLER_MCP_ENABLED!=1",
            )
        ]

    ns = session_ns if session_ns is not None else time.time_ns()
    ctx = render_ctx or make_sim_render_context(run_ns=ns)
    base_sk = f"wechat:{owner_id}:owner-sim-{track.id}-{ns}"
    session_key = base_sk
    results: list[ScenarioCaseResult] = []

    def _send(text: str) -> str:
        return handler.handle_message(
            ctx.render(text),
            session_key=session_key,
            platform="wechat",
            external_id=owner_id,
        ) or ""

    if track.session_mode == "shared":
        for msg in track.setup:
            _send(msg)
        post_cleanup = _cleanup_track_artifacts(track, session_key, ctx)
        if post_cleanup and not post_cleanup[0].startswith("no workspace"):
            print(f"  cleanup {track.id} (post-setup): removed {post_cleanup}")

    for case in track.cases:
        live = render_scenario_case(case, ctx)
        if quick and (not track.quick or live.skip_in_quick or live.tier == "slow"):
            results.append(ScenarioCaseResult(
                name=live.name,
                track_id=track.id,
                ok=True,
                skipped=True,
                skip_reason="quick mode",
            ))
            continue
        if live.requires_mcp and not _mcp_enabled():
            results.append(ScenarioCaseResult(
                name=live.name,
                track_id=track.id,
                ok=True,
                skipped=True,
                skip_reason="requires MCP",
            ))
            continue

        if track.session_mode == "fresh" or live.fresh_session:
            session_key = f"{base_sk}-{live.name}-{time.time_ns()}"
            for msg in track.setup:
                _send(msg)
            post_cleanup = _cleanup_track_artifacts(track, session_key, ctx)
            if post_cleanup and not post_cleanup[0].startswith("no workspace"):
                print(f"  cleanup {track.id}/{live.name}: removed {post_cleanup}")

        t0 = time.time()
        entry = ScenarioCaseResult(name=live.name, track_id=track.id, ok=True)
        try:
            reply = _send(live.user_text)
            elapsed = time.time() - t0
            entry.elapsed_seconds = elapsed
            entry.reply_preview = reply.replace("\n", " ")[:240]
            entry.tools = [
                str(row.get("tool") or "").strip()
                for row in load_current_turn_tool_actions(session_key)
                if str(row.get("tool") or "").strip()
            ]
            if elapsed > live.max_seconds:
                entry.warnings.append(f"slow: {elapsed:.1f}s > {live.max_seconds}s")
            errors, warnings = evaluate_scenario_case(
                entry.tools, reply, live, strict=strict,
            )
            file_errors = _verify_files_on_disk(live, session_key)
            errors.extend(file_errors)
            entry.errors = errors
            entry.warnings.extend(warnings)
            entry.ok = not errors
        except Exception as exc:
            entry.ok = False
            entry.errors.append(str(exc)[:200])
            entry.elapsed_seconds = time.time() - t0
        results.append(entry)

    return results


def run_wechat_scenario_sim(
    manifest: ScenarioManifest,
    *,
    track_ids: tuple[str, ...] | None = None,
    owner_id: str | None = None,
    strict: bool = False,
    quick: bool = False,
) -> ScenarioSimReport:
    from butler.gateway.message_handler import ButlerMessageHandler

    report = ScenarioSimReport()
    if not _has_llm_key():
        report.ok = False
        report.errors.append("no LLM API key in env")
        return report

    owner = (owner_id or os.getenv("BUTLER_OWNER_WECHAT_ID") or "owner-wechat-sim").strip()
    handler = ButlerMessageHandler(channel="gateway")
    want = {t.strip().lower() for t in track_ids} if track_ids else None
    ns = time.time_ns()
    render_ctx = make_sim_render_context(run_ns=ns)

    for track in manifest.tracks:
        if want and track.id.lower() not in want:
            continue
        report.tracks_run += 1
        case_results = run_scenario_track(
            track,
            handler,
            owner_id=owner,
            strict=strict,
            quick=quick,
            session_ns=ns,
            render_ctx=render_ctx,
        )
        for cr in case_results:
            report.cases.append(cr)
            if cr.skipped:
                report.cases_skipped += 1
                continue
            report.cases_run += 1
            if cr.ok:
                report.cases_passed += 1
            else:
                report.ok = False
                for err in cr.errors:
                    report.errors.append(f"{track.id}/{cr.name}: {err}")
            for warn in cr.warnings:
                report.warnings.append(f"{track.id}/{cr.name}: {warn}")

    return report


def list_manifest_tracks(manifest: ScenarioManifest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for track in manifest.tracks:
        out.append({
            "id": track.id,
            "title": track.title,
            "quick": track.quick,
            "requires_mcp": track.requires_mcp,
            "cases": len(track.cases),
            "session_mode": track.session_mode,
        })
    return out


__all__ = [
    "ScenarioCase",
    "ScenarioCaseResult",
    "ScenarioManifest",
    "ScenarioSimReport",
    "ScenarioTrack",
    "SimRenderContext",
    "evaluate_scenario_case",
    "list_manifest_tracks",
    "load_wechat_scenario_manifest",
    "make_sim_render_context",
    "render_scenario_case",
    "run_scenario_track",
    "run_wechat_scenario_sim",
]
