"""Gateway inbound media lines for /诊断 (L1/L9 diagnostic only)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def extend_gateway_media_diagnostic_lines(lines: list[str]) -> None:
    def _run() -> None:
        from butler.gateway.inbound_media import inbound_media_enabled
        from butler.gateway.media_telemetry import format_media_diagnostic_lines
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
            lines.extend(format_media_diagnostic_lines())

    result = safe_best_effort(_run, label="gateway.media_diagnostic", default=False)
    if result is False:
        lines.append("  gateway(入站媒体): 不可用")


__all__ = ["extend_gateway_media_diagnostic_lines"]
