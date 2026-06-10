"""Effective model resolution and ``/model`` command handling (M2 + M3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from butler.config import ModelConfig, get_butler_settings, save_butler_config
import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from butler.config import ButlerSettings
    from butler.project import Project

_ROLE_ALIASES: dict[str, str] = {
    "dev": "dev_agent",
    "content": "content_agent",
    "review": "review_agent",
    "lead": "butler",
}

_LIST_ROLES: tuple[str, ...] = (
    "butler",
    "dev_agent",
    "content_agent",
    "review_agent",
)

_PROJECT_PERSIST_ROLES: frozenset[str] = frozenset(
    {"dev_agent", "content_agent", "review_agent"}
)


@dataclass(frozen=True)
class EffectiveModel:
    """Merged model for a role with provenance labels (inner → outer)."""

    config: ModelConfig
    sources: tuple[str, ...]


def normalize_role(role: str) -> str:
    key = (role or "").strip().lower()
    return _ROLE_ALIASES.get(key, key)


def parse_model_spec(spec: str) -> ModelConfig:
    """Parse ``provider/model`` or ``provider:model`` or bare model name."""
    raw = (spec or "").strip()
    if not raw:
        raise ValueError("模型规格为空")
    if "/" in raw:
        provider, model = raw.split("/", 1)
        return ModelConfig(provider=provider.strip(), model=model.strip())
    if ":" in raw:
        provider, model = raw.split(":", 1)
        return ModelConfig(provider=provider.strip(), model=model.strip())
    return ModelConfig(model=raw)


def resolve_effective_model(
    role: str,
    *,
    project: Project | None = None,
    settings: ButlerSettings | None = None,
) -> EffectiveModel:
    """Merge L0 system → L1 butler YAML → L2 project → L3 runtime (last wins)."""
    settings = settings or get_butler_settings()
    role = normalize_role(role)
    sources: list[str] = []

    cfg = settings._system_default_for_role(role)
    if not cfg.is_empty():
        sources.append("system")

    yaml_layer = settings._yaml_merged_for_role(role)
    if not yaml_layer.is_empty():
        cfg = cfg.merge_with(yaml_layer)
        role_cfg = settings.models.get(role)
        if role_cfg and not role_cfg.is_empty():
            sources.append(f"global:{role}")
        elif not settings.models.butler.is_empty():
            sources.append("global:butler")

    if project is not None:
        if proj_cfg := project.models.get(role):
            if not proj_cfg.is_empty():
                cfg = cfg.merge_with(proj_cfg)
                sources.append(f"project:{project.name}")

    if runtime := settings._runtime_model_overrides.get(role):
        if not runtime.is_empty():
            cfg = cfg.merge_with(runtime)
            sources.append("runtime")

    if not sources:
        sources.append("system")
    return EffectiveModel(config=cfg, sources=tuple(sources))


def _format_sources(sources: tuple[str, ...]) -> str:
    if not sources:
        return "system"
    return " + ".join(sources)


def format_effective_models(
    *,
    project: Project | None = None,
    project_label: str | None = None,
    settings: ButlerSettings | None = None,
) -> str:
    settings = settings or get_butler_settings()
    lines = ["当前有效模型:"]
    if project_label:
        lines[0] += f"（项目: {project_label}）"
    elif project is not None:
        lines[0] += f"（项目: {project.name}）"
    else:
        lines[0] += "（无当前项目 — 厂长/委派均用管家层）"

    for role in _LIST_ROLES:
        em = resolve_effective_model(role, project=project, settings=settings)
        c = em.config
        spec = f"{c.provider or '-'}/{c.model or '-'}"
        lines.append(f"  {role:14} {spec:28} [{_format_sources(em.sources)}]")
    lines.append("")
    lines.append(
        "用法:\n"
        "  /model                          本表\n"
        "  /model <角色> <provider/model>  本会话临时（runtime）\n"
        "  /model save <角色> <p/m>        持久化（butler→~/.butler；dev/content/review→当前项目）\n"
        "  /model reset <角色>             清除临时覆盖"
    )
    return "\n".join(lines)


def format_model_diagnostic_lines(
    *,
    project: Project | None = None,
    settings: ButlerSettings | None = None,
) -> list[str]:
    """Compact model block for ``/诊断`` (no /model usage footer)."""

    settings = settings or get_butler_settings()
    lines = ["--- 有效模型 ---"]
    for role in _LIST_ROLES:
        em = resolve_effective_model(role, project=project, settings=settings)
        c = em.config
        spec = f"{c.provider or '-'}/{c.model or '-'}"
        lines.append(f"  {role}: {spec} [{_format_sources(em.sources)}]")

    try:
        from butler.transport.auxiliary_client import resolve_auxiliary_config

        for task in ("compression", "post_session"):
            aux = resolve_auxiliary_config(task)
            lines.append(
                f"  auxiliary({task}): {aux.provider or '-'}/{aux.model or '-'}"
            )
    except Exception:
        lines.append("  auxiliary: 未配置")

    try:
        from butler.memory.semantic_config import resolve_embedding_config

        ep, em = resolve_embedding_config()
        lines.append(f"  embedding: {ep or '-'}/{em or '-'}")
    except Exception:
        lines.append("  embedding: 未配置")

    try:
        primary = resolve_effective_model("butler", project=project, settings=settings)
        extras = settings.llm_fallback_extra_configs(primary.config)
        if extras:
            fb = ", ".join(f"{c.provider or '-'}/{c.model or '-'}" for c in extras)
            lines.append(f"  llm_fallback: auto → {fb}")
        elif isinstance(settings.llm_fallback, dict) and settings.llm_fallback.get("enabled") is False:
            lines.append("  llm_fallback: 关")
        else:
            lines.append("  llm_fallback: 仅 primary")
    except Exception:
        lines.append("  llm_fallback: 未配置")

    try:
        from butler.gateway_settings import (
            format_gateway_inbound_config_source_line,
            format_gateway_queue_config_source_line,
        )

        lines.append(format_gateway_inbound_config_source_line())
        lines.append(format_gateway_queue_config_source_line())
        from butler.gateway.inbound_media import inbound_media_enabled

        if inbound_media_enabled():
            from butler.gateway_settings import (
                resolve_gateway_inbound_config,
                vision_api_host,
                vision_endpoint_path,
            )

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
            try:
                from butler.gateway.media_telemetry import format_media_diagnostic_lines

                lines.extend(format_media_diagnostic_lines())
            except Exception as exc:
                logger.debug("format model diagnostic lines skipped: %s", exc)
    except Exception:
        lines.append("  gateway(入站媒体): 不可用")

    return lines


def _persist_global_role(settings: ButlerSettings, role: str, cfg: ModelConfig) -> None:
    role = normalize_role(role)
    settings.models.set(role, cfg)
    settings.set_runtime_model_override(role, None)
    save_butler_config()


def _persist_project_role(project: Project, role: str, cfg: ModelConfig) -> None:
    role = normalize_role(role)
    project.set_model(role, cfg)
    get_butler_settings().set_runtime_model_override(role, None)


def handle_model_command(
    arg: str,
    *,
    settings: ButlerSettings | None = None,
    project: Project | None = None,
    project_label: str | None = None,
) -> tuple[str, bool]:
    """Handle ``/model`` body. Returns ``(reply, reset_session_loop)``."""
    settings = settings or get_butler_settings()
    text = (arg or "").strip()
    if not text:
        return format_effective_models(
            project=project,
            project_label=project_label,
            settings=settings,
        ), False

    try:
        from butler.provider_presets import try_handle_preset_model_command

        preset_out = try_handle_preset_model_command(
            text,
            project=project,
            project_label=project_label,
        )
        if preset_out is not None:
            return preset_out
    except Exception as exc:
        logger.debug("handle model command skipped: %s", exc)
    parts = text.split(maxsplit=2)
    verb = parts[0].lower()

    if verb == "reset":
        if len(parts) < 2:
            return "用法: /model reset <角色>", False
        role = normalize_role(parts[1])
        settings.set_runtime_model_override(role, None)
        return f"已清除 {role} 的临时模型覆盖（YAML 未改）。", True

    persist = verb == "save"
    if persist:
        if len(parts) < 3:
            return "用法: /model save <角色> <provider/model>", False
        role = normalize_role(parts[1])
        try:
            cfg = parse_model_spec(parts[2])
        except ValueError as exc:
            return str(exc), False
    else:
        if len(parts) < 2:
            return (
                "用法: /model <角色> <provider/model> 或 /model save … 或 /model reset <角色>",
                False,
            )
        role = normalize_role(parts[0])
        try:
            cfg = parse_model_spec(parts[1])
        except ValueError as exc:
            return str(exc), False

    spec = f"{cfg.provider}/{cfg.model}" if cfg.provider else cfg.model

    if persist:
        if role == "butler":
            _persist_global_role(settings, role, cfg)
            return f"已持久化 {role} → {spec}（~/.butler/config.yaml）", True
        if role in _PROJECT_PERSIST_ROLES:
            if project is None:
                return (
                    f"保存 {role} 需要先 /切换 到项目（写入 project.yaml）。"
                    f" 或 /model save butler … 写管家层。",
                    False,
                )
            _persist_project_role(project, role, cfg)
            return f"已持久化 {role} → {spec}（项目 {project.name}）", True
        return f"未知角色: {role}", False

    settings.set_runtime_model_override(role, cfg)
    return f"已临时设置 {role} → {spec}（本会话 runtime，重启进程后丢失）", True


def workflow_step_spawn_model_config(step_model: ModelConfig | None) -> dict[str, str] | None:
    """Dict for :class:`~butler.task_orchestrator.AgentSpawnConfig.model_config`."""
    if step_model is None or step_model.is_empty():
        return None
    d = step_model.to_dict()
    if not d:
        return None
    return d


def model_config_to_credentials(
    mc: ModelConfig,
    *,
    settings: ButlerSettings | None = None,
) -> dict[str, Any]:
    """Turn ``ModelConfig`` into orchestrator credential kwargs."""
    settings = settings or get_butler_settings()
    prov_name = (mc.provider or settings.default_provider or "").strip()
    pc = settings.providers.get(prov_name) if prov_name else None
    api_key = getattr(pc, "api_key", "") or "" if pc else ""
    base_url = getattr(pc, "base_url", "") or "" if pc else ""
    model = (mc.model or (getattr(pc, "model", "") or "")) if pc else mc.model or ""
    out: dict[str, Any] = {
        "provider": prov_name or None,
        "model": model or "",
        "api_key": api_key,
        "base_url": base_url,
    }
    if mc.max_tokens is not None:
        out["max_tokens"] = mc.max_tokens
    if mc.context_length is not None:
        out["context_length"] = mc.context_length
    return out
