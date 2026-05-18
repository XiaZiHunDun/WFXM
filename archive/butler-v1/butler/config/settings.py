"""Global configuration for Butler System with hierarchical model config."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_BUTLER_HOME = Path.home() / ".butler"


@dataclass
class ProviderConfig:
    name: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Model configuration for a single layer/role. Empty strings mean 'inherit from parent'."""
    provider: str = ""
    model: str = ""
    temperature: float | None = None
    max_tokens: int | None = None

    def is_empty(self) -> bool:
        return not self.provider and not self.model

    def merge_with(self, override: ModelConfig | None) -> ModelConfig:
        """Return a new config with non-empty fields from override taking precedence."""
        if override is None or override.is_empty():
            return ModelConfig(
                provider=self.provider,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        return ModelConfig(
            provider=override.provider or self.provider,
            model=override.model or self.model,
            temperature=override.temperature if override.temperature is not None else self.temperature,
            max_tokens=override.max_tokens if override.max_tokens is not None else self.max_tokens,
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
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ModelConfig:
        if not data:
            return cls()
        return cls(
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            temperature=data.get("temperature"),
            max_tokens=data.get("max_tokens"),
        )


@dataclass
class LayeredModelConfig:
    """Per-role model configs at the butler (system) level."""
    butler: ModelConfig = field(default_factory=ModelConfig)
    dev_agent: ModelConfig = field(default_factory=ModelConfig)
    content_agent: ModelConfig = field(default_factory=ModelConfig)
    review_agent: ModelConfig = field(default_factory=ModelConfig)

    def get(self, role: str) -> ModelConfig:
        return getattr(self, role, self.butler)

    def set(self, role: str, config: ModelConfig) -> None:
        if hasattr(self, role):
            setattr(self, role, config)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for role in ("butler", "dev_agent", "content_agent", "review_agent"):
            cfg = getattr(self, role)
            if not cfg.is_empty():
                d[role] = cfg.to_dict()
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
class Settings:
    butler_home: Path = field(default_factory=lambda: Path(os.getenv("BUTLER_HOME", str(_DEFAULT_BUTLER_HOME))))
    projects_dir: Path = field(default_factory=lambda: Path(os.getenv("BUTLER_PROJECTS_DIR", "./projects")))
    db_path: Path | None = None
    default_provider: str = "minimax"
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    models: LayeredModelConfig = field(default_factory=LayeredModelConfig)
    butler_name: str = "莎丽"
    owner_name: str = "主公"

    def __post_init__(self):
        self.butler_home.mkdir(parents=True, exist_ok=True)
        if self.db_path is None:
            self.db_path = self.butler_home / "butler.db"
        if not self.providers:
            self._load_env_providers()
        if self.models.butler.is_empty() and self.default_provider:
            provider_cfg = self.providers.get(self.default_provider)
            if provider_cfg:
                self.models.butler = ModelConfig(provider=self.default_provider, model=provider_cfg.model)

    def _load_env_providers(self):
        if key := os.getenv("ANTHROPIC_API_KEY"):
            self.providers["claude"] = ProviderConfig(
                name="claude", api_key=key,
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            )
        if key := os.getenv("OPENAI_API_KEY"):
            self.providers["openai"] = ProviderConfig(
                name="openai", api_key=key,
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            )
        if key := os.getenv("DEEPSEEK_API_KEY"):
            self.providers["deepseek"] = ProviderConfig(
                name="deepseek", api_key=key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            )
        if key := os.getenv("DASHSCOPE_API_KEY"):
            self.providers["qwen"] = ProviderConfig(
                name="qwen", api_key=key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model=os.getenv("QWEN_MODEL", "qwen-max"),
            )
        if key := os.getenv("MINIMAX_API_KEY"):
            self.providers["minimax"] = ProviderConfig(
                name="minimax", api_key=key,
                base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1"),
                model=os.getenv("MINIMAX_MODEL", "MiniMax-M2.7"),
            )

    def get_model_config(self, role: str) -> ModelConfig:
        """Get the system-level model config for a given role, falling back to butler config."""
        role_cfg = self.models.get(role)
        if role_cfg.is_empty():
            return self.models.butler
        return self.models.butler.merge_with(role_cfg)

    def save_butler_config(self) -> None:
        """Persist butler-level model config to ~/.butler/config.yaml."""
        config_path = self.butler_home / "config.yaml"
        data: dict[str, Any] = {"models": self.models.to_dict()}
        if self.default_provider:
            data["default_provider"] = self.default_provider
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        instance = cls()
        butler_config = instance.butler_home / "config.yaml"
        if butler_config.exists():
            with open(butler_config, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if "models" in data:
                instance.models = LayeredModelConfig.from_dict(data["models"])
            if "default_provider" in data:
                instance.default_provider = data["default_provider"]
        return instance


settings = Settings.load()
