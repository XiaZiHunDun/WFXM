"""Model resolution diagnostic helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.config import ButlerSettings
    from butler.project import Project

logger = logging.getLogger(__name__)


def append_auxiliary_diagnostic_lines(lines: list[str]) -> None:
    def _run() -> None:
        from butler.transport.auxiliary_client import resolve_auxiliary_config

        for task in ("compression", "post_session"):
            aux = resolve_auxiliary_config(task)
            lines.append(
                f"  auxiliary({task}): {aux.provider or '-'}/{aux.model or '-'}"
            )

    result = safe_best_effort(_run, label="model_resolve.auxiliary", default=False)
    if result is False:
        lines.append("  auxiliary: 未配置")


def append_embedding_diagnostic_line(lines: list[str]) -> None:
    def _run() -> None:
        from butler.memory.semantic_config import resolve_embedding_config

        ep, em = resolve_embedding_config()
        lines.append(f"  embedding: {ep or '-'}/{em or '-'}")

    result = safe_best_effort(_run, label="model_resolve.embedding", default=False)
    if result is False:
        lines.append("  embedding: 未配置")


def append_llm_fallback_diagnostic_line(
    lines: list[str],
    *,
    project: "Project | None",
    settings: "ButlerSettings",
) -> None:
    def _run() -> None:
        from butler.model_resolve import resolve_effective_model

        primary = resolve_effective_model("butler", project=project, settings=settings)
        extras = settings.llm_fallback_extra_configs(primary.config)
        if extras:
            fb = ", ".join(f"{c.provider or '-'}/{c.model or '-'}" for c in extras)
            lines.append(f"  llm_fallback: auto → {fb}")
        elif isinstance(settings.llm_fallback, dict) and settings.llm_fallback.get("enabled") is False:
            lines.append("  llm_fallback: 关")
        else:
            lines.append("  llm_fallback: 仅 primary")

    result = safe_best_effort(_run, label="model_resolve.llm_fallback", default=False)
    if result is False:
        lines.append("  llm_fallback: 未配置")


def extend_gateway_media_diagnostic_lines(lines: list[str]) -> None:
    def _run() -> None:
        from butler.gateway.inbound_media import inbound_media_enabled
        from butler.gateway_settings import (
            format_gateway_inbound_config_source_line,
            format_gateway_queue_config_source_line,
            resolve_gateway_inbound_config,
            vision_api_host,
            vision_endpoint_path,
        )

        lines.append(format_gateway_inbound_config_source_line())
        lines.append(format_gateway_queue_config_source_line())
        if inbound_media_enabled():
            gw = resolve_gateway_inbound_config()
            lines.append(
                f"  gateway(识图): {gw.vision.provider} VLM @ "
                f"{vision_api_host()}/v1/{vision_endpoint_path()}"
            )
            ilink = "iLink 优先" if gw.speech.prefer_ilink_text else "本地 STT 优先"
            lines.append(
                f"  gateway(语音): {ilink}; STT={gw.speech.stt_provider}; "
                f"whisper={gw.speech.whisper_model}"
            )
            from butler.gateway.media_telemetry import format_media_diagnostic_lines

            lines.extend(format_media_diagnostic_lines())

    result = safe_best_effort(_run, label="model_resolve.gateway_media", default=False)
    if result is False:
        lines.append("  gateway(入站媒体): 不可用")


def try_handle_preset_model_command_safe(
    text: str,
    *,
    project: "Project | None",
    project_label: str | None,
) -> tuple[str, bool] | None:
    def _run() -> tuple[str, bool] | None:
        from butler.provider_presets import try_handle_preset_model_command

        return try_handle_preset_model_command(
            text,
            project=project,
            project_label=project_label,
        )

    return safe_best_effort(_run, label="model_resolve.preset_command", default=None)
