"""Butler Provider Registry.

Lightweight provider profile registry. Each provider maps a name
to api_mode, base_url, env_var for API key, etc.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProviderProfile:
    name: str
    api_mode: str = "chat_completions"
    aliases: tuple = ()
    base_url: str = ""
    env_vars: tuple = ()
    default_model: str = ""
    default_max_tokens: Optional[int] = None

    def resolve_api_key(self) -> Optional[str]:
        for var in self.env_vars:
            val = os.environ.get(var)
            if val:
                return val
        return None


_REGISTRY: Dict[str, ProviderProfile] = {}
_ALIASES: Dict[str, str] = {}


def register_provider(profile: ProviderProfile) -> None:
    _REGISTRY[profile.name] = profile
    for alias in profile.aliases:
        _ALIASES[alias] = profile.name


def get_provider(name: str) -> Optional[ProviderProfile]:
    if not _REGISTRY:
        _register_builtin()
    canonical = _ALIASES.get(name, name)
    return _REGISTRY.get(canonical)


def list_providers() -> List[ProviderProfile]:
    if not _REGISTRY:
        _register_builtin()
    return list(_REGISTRY.values())


def _register_builtin() -> None:
    """Register commonly used providers."""
    builtins = [
        ProviderProfile(
            name="deepseek",
            aliases=("deepseek-chat",),
            base_url="https://api.deepseek.com/v1",
            env_vars=("DEEPSEEK_API_KEY",),
            default_model="deepseek-chat",
        ),
        ProviderProfile(
            name="minimax",
            aliases=("mini-max",),
            api_mode="chat_completions",
            base_url="https://api.minimax.chat/v1",
            env_vars=("MINIMAX_API_KEY",),
            default_model="MiniMax-M2.7",
            default_max_tokens=4096,
        ),
        ProviderProfile(
            name="minimax-cn",
            aliases=("minimax-china", "minimax_cn"),
            api_mode="chat_completions",
            base_url="https://api.minimaxi.com/v1",
            env_vars=("MINIMAX_CN_API_KEY",),
            default_model="MiniMax-M2.7",
            default_max_tokens=4096,
        ),
        ProviderProfile(
            name="openai",
            aliases=("gpt",),
            base_url="https://api.openai.com/v1",
            env_vars=("OPENAI_API_KEY",),
            default_model="gpt-4o",
        ),
        ProviderProfile(
            name="anthropic",
            aliases=("claude",),
            api_mode="anthropic_messages",
            base_url="https://api.anthropic.com",
            env_vars=("ANTHROPIC_API_KEY",),
            default_model="claude-sonnet-4-20250514",
            default_max_tokens=4096,
        ),
        ProviderProfile(
            name="qwen",
            aliases=("tongyi", "dashscope"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            env_vars=("DASHSCOPE_API_KEY", "QWEN_API_KEY"),
            default_model="qwen-max",
        ),
        ProviderProfile(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            env_vars=("OPENROUTER_API_KEY",),
        ),
        ProviderProfile(
            name="siliconflow",
            aliases=("silicon",),
            base_url="https://api.siliconflow.cn/v1",
            env_vars=("SILICONFLOW_API_KEY",),
        ),
        ProviderProfile(
            name="zhipu",
            aliases=("glm", "chatglm"),
            base_url="https://open.bigmodel.cn/api/paas/v4",
            env_vars=("ZHIPU_API_KEY",),
            default_model="glm-4-plus",
        ),
    ]
    for p in builtins:
        register_provider(p)
