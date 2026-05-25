"""``butler://`` provider preset library (cc-switch / 主线 G P2 subset)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.project import Project

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


def preset_to_model_config(preset: ProviderPreset) -> ModelConfig:
    from butler.config import ModelConfig

    return ModelConfig(
        provider=str(preset.provider or "").strip(),
        model=str(preset.model or "").strip(),
    )


def apply_provider_preset(
    preset_id: str,
    *,
    role: str = "dev_agent",
    project: Any | None = None,
    workspace: Path | None = None,
    persist: bool = True,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Apply ``butler://`` preset to ``project.yaml`` (or runtime if ``persist=False``)."""
    from butler.config import get_butler_settings
    from butler.model_resolve import normalize_role
    from butler.project import Project

    preset = resolve_preset(preset_id)
    if preset is None:
        return False, f"未找到预设: {preset_id}"
    role_n = normalize_role(role)
    cfg = preset_to_model_config(preset)
    if cfg.is_empty():
        return False, f"预设 {format_preset_uri(preset)} 缺少 provider/model"
    spec = f"{cfg.provider}/{cfg.model}" if cfg.provider else cfg.model
    uri = format_preset_uri(preset)

    proj = project
    if proj is None and workspace is not None:
        ws = workspace.expanduser().resolve()
        cfg_path = ws / "project.yaml"
        if not cfg_path.is_file():
            return False, f"未找到 project.yaml: {cfg_path}"
        proj = Project.from_yaml(cfg_path)

    if dry_run:
        target = f"project {proj.name}" if proj is not None else "runtime"
        return True, f"[dry-run] 将应用 {uri} → {role_n} ({spec}) 到 {target}"

    settings = get_butler_settings()
    if persist:
        if role_n == "butler":
            from butler.model_resolve import _persist_global_role

            _persist_global_role(settings, role_n, cfg)
            return True, f"已应用 {uri} → butler（~/.butler/config.yaml）"
        if proj is None:
            return (
                False,
                f"持久化 {role_n} 需要项目：先 /切换 项目，或使用 "
                f"`butler provider apply {uri} --workspace <path>`。",
            )
        proj.set_model(role_n, cfg)
        settings.set_runtime_model_override(role_n, None)
        return True, f"已应用 {uri} → {role_n}（项目 {proj.name}，project.yaml）"

    settings.set_runtime_model_override(role_n, cfg)
    return True, f"已临时应用 {uri} → {role_n}（本会话 runtime）"


def try_handle_preset_model_command(
    text: str,
    *,
    project: Any | None = None,
    project_label: str | None = None,
) -> tuple[str, bool] | None:
    """Parse ``preset <id> [role]`` or ``butler://…`` for ``/model`` / ``/模型``."""
    from butler.model_resolve import normalize_role

    raw = (text or "").strip()
    if not raw:
        return None
    persist = False
    if raw.lower().startswith("save "):
        persist = True
        raw = raw[5:].strip()
    preset_id = ""
    role = "dev_agent"
    if raw.startswith("butler://"):
        preset_id = raw
        rest = ""
    else:
        parts = raw.split(maxsplit=2)
        if not parts or parts[0].lower() != "preset":
            return None
        if len(parts) < 2:
            return (
                "用法: /模型 preset <butler://id 或 preset_id> [角色]\n"
                "  或 /模型 save preset <id> [角色] 写入 project.yaml",
                False,
            )
        preset_id = parts[1]
        rest = parts[2] if len(parts) > 2 else ""
    if rest:
        role = normalize_role(rest)
    ok, msg = apply_provider_preset(
        preset_id,
        role=role,
        project=project,
        persist=persist,
    )
    if not ok:
        return msg, False
    label = project_label or (getattr(project, "name", None) if project else None)
    if label:
        msg = f"{msg}\n（当前项目: {label}）"
    return msg, True


__all__ = [
    "ProviderPreset",
    "apply_provider_preset",
    "format_preset_uri",
    "format_presets_list",
    "load_presets",
    "preset_to_model_config",
    "presets_path",
    "resolve_preset",
    "try_handle_preset_model_command",
]
