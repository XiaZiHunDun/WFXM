"""Per-model context transform registry (MOD-5/6)."""

from __future__ import annotations

import fnmatch
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml  # type: ignore[import-untyped]

from butler.contracts.context_transform_ports import ContextTransformPort, TransformContext

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_BUILTIN_TRANSFORMS: dict[str, Callable[[], ContextTransformPort]] = {}
_CONFIG_MTIME: float = 0.0
_CONFIG_PROFILES: list[dict[str, Any]] = []


@dataclass
class _FnTransform:
    """Adapter wrapping a plain callable as ContextTransformPort."""

    transform_id: str
    priority: int
    lossy: bool
    fn: Callable[[list[dict[str, Any]], TransformContext], list[dict[str, Any]]]

    def apply(self, messages: list[dict[str, Any]], ctx: TransformContext) -> list[dict[str, Any]]:
        return self.fn(messages, ctx)


def register_builtin_transform(
    transform_id: str,
    factory: Callable[[], ContextTransformPort],
) -> None:
    with _lock:
        _BUILTIN_TRANSFORMS[transform_id] = factory


def _default_config_path() -> Path:
    from butler.config import get_butler_home

    return Path(get_butler_home()) / "model-transforms.yaml"


def _load_config_profiles(path: Path | None = None) -> list[dict[str, Any]]:
    global _CONFIG_MTIME, _CONFIG_PROFILES
    cfg_path = path or _default_config_path()
    if not cfg_path.is_file():
        _CONFIG_PROFILES = []
        _CONFIG_MTIME = 0.0
        return []
    mtime = cfg_path.stat().st_mtime
    if mtime == _CONFIG_MTIME and _CONFIG_PROFILES:
        return _CONFIG_PROFILES
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    profiles = data.get("profiles") or []
    if not isinstance(profiles, list):
        profiles = []
    _CONFIG_PROFILES = profiles
    _CONFIG_MTIME = mtime
    return profiles


def reload_transform_registry(path: Path | None = None) -> int:
    """Force reload YAML profiles; returns profile count."""
    global _CONFIG_MTIME
    _CONFIG_MTIME = 0.0
    return len(_load_config_profiles(path))


def _match_profile(provider: str, model: str, profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    prov = (provider or "").lower()
    mod = model or ""
    for profile in profiles:
        match = profile.get("match") or {}
        p_pat = str(match.get("provider") or "*").lower()
        m_pat = str(match.get("model") or "*")
        if p_pat not in ("*", prov) and prov != p_pat:
            continue
        if m_pat != "*" and not fnmatch.fnmatch(mod, m_pat):
            continue
        return profile
    return None


def _resolve_transform_chain(
    provider: str,
    model: str,
    *,
    path: Path | None = None,
) -> list[tuple[ContextTransformPort, dict[str, Any]]]:
    profiles = _load_config_profiles(path)
    profile = _match_profile(provider, model, profiles)
    entries: list[tuple[str, dict[str, Any], int]] = []
    if profile:
        for item in profile.get("transforms") or []:
            if not isinstance(item, dict):
                continue
            tid = str(item.get("id") or "").strip()
            if not tid:
                continue
            raw_params = item.get("params")
            params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
            prio = int(item.get("priority", 100))
            entries.append((tid, params, prio))
    else:
        entries.append(("thinking_protocol", {}, 50))
    chain: list[tuple[ContextTransformPort, dict[str, Any]]] = []
    with _lock:
        for tid, params, prio in sorted(entries, key=lambda x: x[2]):
            factory = _BUILTIN_TRANSFORMS.get(tid)
            if factory is None:
                logger.debug("Unknown transform id: %s", tid)
                continue
            t = factory()
            chain.append((t, params))
    return chain


def apply_model_transforms(
    messages: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
    diagnostics: dict[str, Any] | None = None,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Run matched transform chain on API messages."""
    from butler.core.transform_overrides import merge_transform_params

    out = list(messages)
    chain = _resolve_transform_chain(provider, model, path=path)
    applied: list[str] = []
    for transform, params in chain:
        merged = merge_transform_params(transform.transform_id, params)
        ctx = TransformContext(
            provider=provider,
            model=model,
            params=merged,
            diagnostics=diagnostics,
        )
        out = transform.apply(out, ctx)
        applied.append(transform.transform_id)
    if diagnostics is not None:
        diagnostics["model_transforms"] = applied
        diagnostics["model_transform_profile"] = f"{provider}/{model}"
    return out


def refresh_model_binding(loop: Any) -> None:
    """Sync context window + transform registry after model/client change."""
    reload_transform_registry()
    client = getattr(loop, "client", None)
    if client is None:
        return
    provider = str(getattr(client, "provider_name", "") or getattr(client, "provider", "") or "")
    model = str(getattr(client, "model", "") or "")
    from butler.core.context_transform_registry_ops import infer_context_length_safe

    infer_context_length_safe(loop, provider=provider, model=model)
    if getattr(loop, "diagnostics", None) is not None:
        loop.diagnostics["active_model"] = f"{provider}/{model}"


def _thinking_protocol_transform(messages: list[dict[str, Any]], ctx: TransformContext) -> list[dict[str, Any]]:
    from butler.transport.thinking_protocol import maybe_append_thinking_system_hint

    out: list[dict[str, Any]] = []
    for msg in messages:
        copy = dict(msg)
        if copy.get("role") == "system":
            copy["content"] = maybe_append_thinking_system_hint(
                str(copy.get("content") or ""),
                provider=ctx.provider,
                model=ctx.model,
            )
        out.append(copy)
    return out


def _fc_hint_extra_transform(messages: list[dict[str, Any]], ctx: TransformContext) -> list[dict[str, Any]]:
    from butler.agent_profiles import get_model_aware_prompt_extra

    extra = get_model_aware_prompt_extra(ctx.provider)
    if not extra:
        return list(messages)
    out: list[dict[str, Any]] = []
    for msg in messages:
        copy = dict(msg)
        if copy.get("role") == "system":
            body = str(copy.get("content") or "")
            if extra.strip() not in body:
                copy["content"] = body.rstrip() + extra
        out.append(copy)
    return out


def _register_defaults() -> None:
    register_builtin_transform(
        "thinking_protocol",
        lambda: _FnTransform(
            transform_id="thinking_protocol",
            priority=50,
            lossy=False,
            fn=_thinking_protocol_transform,
        ),
    )
    register_builtin_transform(
        "fc_hint_extra",
        lambda: _FnTransform(
            transform_id="fc_hint_extra",
            priority=60,
            lossy=False,
            fn=_fc_hint_extra_transform,
        ),
    )


_register_defaults()
