"""``butler://`` provider preset library (cc-switch / 主线 G P2 subset)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from butler.config import get_butler_home


@dataclass(frozen=True)
class ProviderPreset:
    preset_id: str
    provider: str
    model: str = ""
    base_url: str = ""
    description: str = ""


def presets_path() -> Path:
    return get_butler_home() / "provider-presets.yaml"


def _builtin_presets() -> list[ProviderPreset]:
    return [
        ProviderPreset("minimax-default", "minimax", model="", description="默认 MiniMax"),
        ProviderPreset("deepseek-chat", "deepseek", model="deepseek-chat", description="DeepSeek 对话"),
        ProviderPreset("openai-gpt4o", "openai", model="gpt-4o", description="OpenAI GPT-4o"),
    ]


def load_presets() -> list[ProviderPreset]:
    path = presets_path()
    if not path.is_file():
        return _builtin_presets()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return _builtin_presets()
    block = data.get("presets")
    if not isinstance(block, dict):
        return _builtin_presets()
    out: list[ProviderPreset] = []
    for pid, raw in block.items():
        if not isinstance(raw, dict):
            continue
        out.append(
            ProviderPreset(
                preset_id=str(pid),
                provider=str(raw.get("provider") or ""),
                model=str(raw.get("model") or ""),
                base_url=str(raw.get("base_url") or ""),
                description=str(raw.get("description") or ""),
            )
        )
    return out or _builtin_presets()


def format_preset_uri(preset: ProviderPreset) -> str:
    return f"butler://{preset.preset_id}"


def format_presets_list() -> str:
    lines = ["Provider 预设（butler://）:"]
    for p in load_presets():
        uri = format_preset_uri(p)
        desc = f" — {p.description}" if p.description else ""
        model = f" ({p.model})" if p.model else ""
        lines.append(f"  • {uri}: {p.provider}{model}{desc}")
    lines.append(f"\n自定义: {presets_path()}")
    return "\n".join(lines)


def resolve_preset(preset_id: str) -> ProviderPreset | None:
    key = str(preset_id or "").strip().removeprefix("butler://")
    for p in load_presets():
        if p.preset_id == key:
            return p
    return None


__all__ = [
    "ProviderPreset",
    "format_preset_uri",
    "format_presets_list",
    "load_presets",
    "presets_path",
    "resolve_preset",
]
