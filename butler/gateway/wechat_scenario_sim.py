"""WeChat owner scenario simulation via ButlerMessageHandler (no iLink).

Manifest SSOT: ``.butler/simulation/wechat-owner-scenarios.yaml``

Deprecated: Use `butler.gateway.wechat_scenario_sim` package instead.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.gateway.wechat_scenario_sim module is deprecated, "
    "use butler.gateway.wechat_scenario_sim package instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.gateway.wechat_scenario_sim.__init__ import (
    FileContainsSpec,
    ScenarioCase,
    ScenarioCaseResult,
    ScenarioManifest,
    ScenarioSimReport,
    ScenarioTrack,
    SessionMode,
    SimRenderContext,
    Tier,
    evaluate_outbound_capture,
    evaluate_scenario_case,
    evaluation_reply_text,
    list_manifest_tracks,
    load_turn_tools,
    load_wechat_scenario_manifest,
    make_sim_render_context,
    render_scenario_case,
    resolve_handler_session_key,
    run_scenario_track,
    run_wechat_scenario_sim,
)

__all__ = [
    "FileContainsSpec",
    "ScenarioCase",
    "ScenarioCaseResult",
    "ScenarioManifest",
    "ScenarioSimReport",
    "ScenarioTrack",
    "SessionMode",
    "SimRenderContext",
    "Tier",
    "evaluate_outbound_capture",
    "evaluate_scenario_case",
    "evaluation_reply_text",
    "list_manifest_tracks",
    "load_turn_tools",
    "load_wechat_scenario_manifest",
    "make_sim_render_context",
    "render_scenario_case",
    "resolve_handler_session_key",
    "run_scenario_track",
    "run_wechat_scenario_sim",
]