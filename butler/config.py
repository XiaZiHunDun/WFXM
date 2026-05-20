"""Butler user configuration, layered model defaults, and environment-backed providers.

Reads ``~/.butler/config.yaml`` (root override: ``BUTLER_HOME``). Project roots default
to ``<workspace>/projects/`` (same layout as this repository).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml
from dotenv import load_dotenv

from butler.paths import resolve_hermes_home

load_dotenv()

_ROLE_NAMES: Final[tuple[str, ...]] = (
    "butler",
    "dev_agent",
    "content_agent",
    "review_agent",
)

_DEFAULT_BUTLER_HOME = Path.home() / ".butler"


def _workspace_root() -> Path:
    """Repository / workspace root containing ``butler/`` and ``projects/``."""
    return Path(__file__).resolve().parent.parent


def _default_projects_dir() -> Path:
    env = os.getenv("BUTLER_PROJECTS_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return _workspace_root() / "projects"


@dataclass
class ModelConfig:
    """Per-role LLM parameters. Empty strings / unset numerics inherit from parent layer."""

    provider: str = ""
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None
    context_length: int | None = None

    def is_empty(self) -> bool:
        return not self.provider and not self.model

    def merge_with(self, override: ModelConfig | None) -> ModelConfig:
        """Return a new config with non-empty fields from ``override`` taking precedence."""
        if override is None or override.is_empty():
            return ModelConfig(
                provider=self.provider,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                context_length=self.context_length,
            )
        return ModelConfig(
            provider=override.provider or self.provider,
            model=override.model or self.model,
            temperature=override.temperature if override.temperature is not None else self.temperature,
            max_tokens=override.max_tokens if override.max_tokens is not None else self.max_tokens,
            context_length=override.context_length if override.context_length is not None else self.context_length,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.provider:
            d["provider"] = self.provider
        if self.model:
            d["model"] = self.model
        if self.temperature is not None:
            d["temperature"] = self.temperature
        if self.max_tokens is not None:
            d["max_tokens"] = self.max_tokens
        if self.context_length is not None:
            d["context_length"] = self.context_length
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ModelConfig:
        if not data:
            return cls()
        return cls(
            provider=str(data.get("provider", "") or ""),
            model=str(data.get("model", "") or ""),
            temperature=data.get("temperature"),
            max_tokens=data.get("max_tokens"),
            context_length=data.get("context_length"),
        )


@dataclass
class LayeredModelConfig:
    """Per-role model configs at the Butler (user) level."""

    butler: ModelConfig = field(default_factory=ModelConfig)
    dev_agent: ModelConfig = field(default_factory=ModelConfig)
    content_agent: ModelConfig = field(default_factory=ModelConfig)
    review_agent: ModelConfig = field(default_factory=ModelConfig)

    def get(self, role: str) -> ModelConfig:
        if role in _ROLE_NAMES:
            return getattr(self, role)
        return self.butler

    def set(self, role: str, config: ModelConfig) -> None:
        if hasattr(self, role):
            setattr(self, role, config)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for r in _ROLE_NAMES:
            cfg = getattr(self, r)
            if not cfg.is_empty():
                d[r] = cfg.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LayeredModelConfig:
        if not data:
            return cls()
        return cls(
            butler=ModelConfig.from_dict(data.get("butler")),
            dev_agent=ModelConfig.from_dict(data.get("dev_agent")),
            content_agent=ModelConfig.from_dict(data.get("content_agent")),
            review_agent=ModelConfig.from_dict(data.get("review_agent")),
        )


@dataclass
class ProviderConfig:
    """API credentials and defaults for a provider (from env + optional YAML later)."""

    name: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ButlerSettings:
    """Loaded Butler configuration with env + ``~/.butler/config.yaml`` + runtime overrides."""

    butler_home: Path = field(default_factory=lambda: Path(os.getenv("BUTLER_HOME", str(_DEFAULT_BUTLER_HOME))).expanduser())
    projects_dir: Path = field(default_factory=_default_projects_dir)
    db_path: Path | None = None
    default_provider: str = "minimax"
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    models: LayeredModelConfig = field(default_factory=LayeredModelConfig)
    butler_name: str = "莎丽"
    owner_name: str = "主公"
    _runtime_model_overrides: dict[str, ModelConfig] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.butler_home = self.butler_home.expanduser().resolve()
        self.butler_home.mkdir(parents=True, exist_ok=True)
        self.projects_dir = self.projects_dir.expanduser().resolve()
        if self.db_path is None:
            self.db_path = self.butler_home / "state.db"
        else:
            self.db_path = self.db_path.expanduser().resolve()
        if not self.providers:
            self._load_env_providers()
        self._ensure_default_models_from_provider()

    @property
    def config_yaml_path(self) -> Path:
        return self.butler_home / "config.yaml"

    def _load_env_providers(self) -> None:
        if key := os.getenv("ANTHROPIC_API_KEY"):
            self.providers["claude"] = ProviderConfig(
                name="claude",
                api_key=key,
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            )
        if key := os.getenv("OPENAI_API_KEY"):
            self.providers["openai"] = ProviderConfig(
                name="openai",
                api_key=key,
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            )
        if key := os.getenv("DEEPSEEK_API_KEY"):
            self.providers["deepseek"] = ProviderConfig(
                name="deepseek",
                api_key=key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            )
        if key := os.getenv("DASHSCOPE_API_KEY"):
            self.providers["qwen"] = ProviderConfig(
                name="qwen",
                api_key=key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model=os.getenv("QWEN_MODEL", "qwen-max"),
            )
        if key := os.getenv("MINIMAX_API_KEY"):
            self.providers["minimax"] = ProviderConfig(
                name="minimax",
                api_key=key,
                base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"),
                model=os.getenv("MINIMAX_MODEL", "MiniMax-M2.7"),
            )

    def _ensure_default_models_from_provider(self) -> None:
        if not self.models.butler.is_empty():
            return
        if self.default_provider and (pc := self.providers.get(self.default_provider)):
            self.models.butler = ModelConfig(provider=self.default_provider, model=pc.model)

    def _system_default_for_role(self, role: str) -> ModelConfig:
        """Layer 1: implicit defaults from ``default_provider`` + provider env."""
        del role  # same system default for each role unless YAML specializes
        if self.default_provider and (pc := self.providers.get(self.default_provider)):
            return ModelConfig(provider=self.default_provider, model=pc.model)
        return ModelConfig()

    def _yaml_merged_for_role(self, role: str) -> ModelConfig:
        """Layer 2: YAML ``models`` layering (inherits from Butler role defaults)."""
        role_cfg = self.models.get(role)
        if role_cfg.is_empty():
            return self.models.butler
        return self.models.butler.merge_with(role_cfg)

    def set_runtime_model_override(self, role: str, cfg: ModelConfig | None) -> None:
        """Layer 3: in-process overrides ( cleared with ``None`` )."""
        if cfg is None or cfg.is_empty():
            self._runtime_model_overrides.pop(role, None)
        else:
            self._runtime_model_overrides[role] = cfg

    def clear_runtime_model_overrides(self) -> None:
        self._runtime_model_overrides.clear()

    def get_model_config(self, role: str) -> ModelConfig:
        """Merged model config: system defaults → ``config.yaml`` → runtime override."""
        merged = self._system_default_for_role(role).merge_with(self._yaml_merged_for_role(role))
        if override := self._runtime_model_overrides.get(role):
            merged = merged.merge_with(override)
        return merged

    def save_butler_config(self) -> None:
        """Persist Butler settings to ``~/.butler/config.yaml``."""
        self.butler_home.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "butler_name": self.butler_name,
            "owner_name": self.owner_name,
            "models": self.models.to_dict(),
        }
        if self.default_provider:
            data["default_provider"] = self.default_provider
        path = self.config_yaml_path
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _apply_yaml_dict(self, data: dict[str, Any]) -> None:
        self.butler_name = str(data.get("butler_name", self.butler_name))
        self.owner_name = str(data.get("owner_name", self.owner_name))
        self.default_provider = str(data.get("default_provider", self.default_provider))
        if "models" in data and isinstance(data["models"], dict):
            self.models = LayeredModelConfig.from_dict(data["models"])
        self._ensure_default_models_from_provider()

    @classmethod
    def load(cls, config_yaml: Path | None = None) -> ButlerSettings:
        """Load Butler settings from env, then optional YAML."""
        instance = cls()
        path = config_yaml or instance.config_yaml_path
        if path.exists():
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if isinstance(raw, dict):
                instance._apply_yaml_dict(raw)
        return instance


_settings: ButlerSettings | None = None


def get_butler_settings() -> ButlerSettings:
    """Singleton Butler settings shared across Butler modules."""
    global _settings
    if _settings is None:
        _settings = ButlerSettings.load()
    return _settings


def reload_butler_settings() -> ButlerSettings:
    """Reload from disk (new singleton)."""
    global _settings
    _settings = ButlerSettings.load()
    return _settings


def save_butler_config() -> None:
    """Persist global Butler settings singleton to ``~/.butler/config.yaml``."""
    get_butler_settings().save_butler_config()


def hermes_home_display() -> str:
    """Resolved Hermes home path (Gateway legacy co-install only)."""
    return str(resolve_hermes_home())


def get_model_config(role: str) -> ModelConfig:
    """Return merged model configuration for ``role`` (see ``ButlerSettings``)."""
    return get_butler_settings().get_model_config(role)


def get_butler_home() -> Path:
    """``~/.butler/`` (via ``BUTLER_HOME`` when set)."""
    return get_butler_settings().butler_home


__all__ = [
    "ButlerSettings",
    "LayeredModelConfig",
    "ModelConfig",
    "ProviderConfig",
    "get_butler_home",
    "get_butler_settings",
    "get_model_config",
    "reload_butler_settings",
    "save_butler_config",
    "hermes_home_display",
]
