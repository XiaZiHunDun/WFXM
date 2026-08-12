from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.wechat_scenario_sim_bridge import run_handler_with_outbound_sim
from butler.gateway.wechat_scenario_sim_ops import run_scenario_case_safe
from butler.project.manager import ProjectManager
from butler.defaults.env_defaults import (
    MCP_ENABLED_DEFAULT,
    OWNER_WECHAT_ID_DEFAULT,
)

from .evaluation import evaluate_outbound_capture, evaluate_scenario_case, evaluation_reply_text
from .render import SimRenderContext, make_sim_render_context, render_scenario_case
from .schema import ScenarioCase, ScenarioCaseResult, ScenarioManifest, ScenarioSimReport, ScenarioTrack
from .utils import _audit_event_count, load_turn_tools, resolve_handler_session_key


def _mcp_enabled() -> bool:
    return os.getenv("BUTLER_MCP_ENABLED", MCP_ENABLED_DEFAULT).strip() == "1"


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


def _project_workspace(session_key: str, *, handler: Any | None = None, owner_id: str = "") -> Path | None:
    sk = session_key
    if handler is not None and owner_id:
        sk = resolve_handler_session_key(handler, owner_id=owner_id, session_key=session_key)
    proj = ProjectManager().get_current(session_key=sk)
    if proj is None:
        return None
    return Path(proj.workspace)


def _verify_files_on_disk(
    case: ScenarioCase,
    session_key: str,
    *,
    handler: Any | None = None,
    owner_id: str = "",
) -> list[str]:
    errors: list[str] = []
    if (
        not case.verify_files_exist
        and not case.verify_files_missing
        and not case.verify_file_contains
    ):
        return errors
    ws = _project_workspace(session_key, handler=handler, owner_id=owner_id)
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
    for spec in case.verify_file_contains:
        path = (ws / spec.path).resolve()
        if not path.is_file():
            errors.append(f"file missing for content check: {spec.path}")
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"cannot read {spec.path}: {exc}")
            continue
        if spec.substrings and not any(needle in body for needle in spec.substrings):
            errors.append(
                f"file {spec.path} missing any of {spec.substrings}"
            )
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
    track_owner = owner_id
    if track.id == "h-onboarding":
        track_owner = f"owner-sim-onboarding-{format(ns % 0xFFFFFF, '06x')}"
        base_sk = f"wechat:{track_owner}:owner-sim-{track.id}-{ns}"
    session_key = base_sk
    results: list[ScenarioCaseResult] = []

    def _send(text: str) -> str:
        return handler.handle_message(
            ctx.render(text),
            session_key=session_key,
            platform="wechat",
            external_id=track_owner,
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
            if track.session_mode == "fresh":
                post_cleanup = _cleanup_track_artifacts(track, session_key, ctx)
                if post_cleanup and not post_cleanup[0].startswith("no workspace"):
                    print(f"  cleanup {track.id}/{live.name}: removed {post_cleanup}")

        t0 = time.time()
        entry = ScenarioCaseResult(name=live.name, track_id=track.id, ok=True)

        def _run_case() -> None:
            audit_before = _audit_event_count(
                handler,
                owner_id=owner_id,
                session_key=session_key,
            )
            outbound_sim = track.simulate_wechat_outbound or live.simulate_wechat_outbound
            if outbound_sim:
                def _dispatch() -> str:
                    return handler.handle_message(
                        ctx.render(live.user_text),
                        session_key=session_key,
                        platform="wechat",
                        external_id=track_owner,
                    ) or ""

                reply, capture = run_handler_with_outbound_sim(
                    _dispatch,
                    chat_id=track_owner,
                    ack_seconds=3.0,
                    wait_delegate_seconds=live.max_seconds,
                )
                entry.outbound_count = len(capture.bodies)
                if capture.bodies:
                    entry.outbound_preview = " | ".join(
                        b.replace("\n", " ")[:80] for b in capture.bodies
                    )[:240]
            else:
                reply = _send(live.user_text)
            elapsed = time.time() - t0
            entry.elapsed_seconds = elapsed
            entry.reply_preview = reply.replace("\n", " ")[:240]
            entry.tools = load_turn_tools(
                handler,
                owner_id=owner_id,
                session_key=session_key,
                audit_before=audit_before,
            )
            if elapsed > live.max_seconds:
                entry.warnings.append(f"slow: {elapsed:.1f}s > {live.max_seconds}s")
            eval_reply = evaluation_reply_text(
                handler,
                owner_id=owner_id,
                session_key=session_key,
                reply=reply,
                tools=entry.tools,
            )
            errors, warnings = evaluate_scenario_case(
                entry.tools, eval_reply, live, strict=strict,
            )
            if outbound_sim:
                errors.extend(evaluate_outbound_capture(
                    capture.bodies if outbound_sim else [],
                    live,
                ))
            file_errors = _verify_files_on_disk(
                live, session_key, handler=handler, owner_id=owner_id,
            )
            errors.extend(file_errors)
            entry.errors = errors
            entry.warnings.extend(warnings)
            entry.ok = not errors
            if not entry.ok and live.prompt_hint:
                entry.warnings.insert(0, f"prompt_hint: {live.prompt_hint}")

        run_scenario_case_safe(_run_case, entry, t0=t0)
        results.append(entry)

    return results


def run_wechat_scenario_sim(
    manifest: ScenarioManifest,
    *,
    track_ids: tuple[str, ...] | None = None,
    owner_id: str | None = None,
    strict: bool = False,
    quick: bool = False,
    require_llm: bool = True,
) -> ScenarioSimReport:

    report = ScenarioSimReport()
    if require_llm and not _has_llm_key():
        report.ok = False
        report.errors.append("no LLM API key in env")
        return report

    owner = (owner_id or os.getenv("BUTLER_OWNER_WECHAT_ID", OWNER_WECHAT_ID_DEFAULT) or "owner-wechat-sim").strip()
    from butler.gateway.gateway_contracts import register_gateway_contracts

    register_gateway_contracts()
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
