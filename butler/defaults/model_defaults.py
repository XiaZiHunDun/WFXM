"""Single place for model-related literal defaults (L0 / gateway / embedding / fallback).

Business modules should not scatter provider/model strings; import from here or
resolve via ``resolve_effective_model`` / ``resolve_*_config`` helpers.
"""

from __future__ import annotations

from typing import Final

DEFAULT_PROVIDER: Final[str] = "minimax"

PROVIDER_ENV_DEFAULT_MODEL: Final[dict[str, str]] = {
    "claude": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "deepseek": "deepseek-chat",
    "qwen": "qwen-max",
    "minimax": "MiniMax-M2.7",
}

AUTO_FALLBACK_PROVIDERS: Final[tuple[str, ...]] = ("deepseek", "qwen", "openai")

AUXILIARY_SCAN_PROVIDERS: Final[tuple[str, ...]] = (
    "minimax",
    "deepseek",
    "openai",
    "claude",
)

DEFAULT_EMBEDDING_PROVIDER: Final[str] = "local"
DEFAULT_EMBEDDING_MODEL: Final[str] = "hashing-v1"

OPENAI_EMBEDDING_MODEL: Final[str] = "text-embedding-3-small"
MINIMAX_EMBEDDING_MODEL: Final[str] = "embo-01"
QWEN_EMBEDDING_MODEL: Final[str] = "text-embedding-v3"

GATEWAY_VISION_PROVIDER: Final[str] = "minimax"
GATEWAY_VISION_ENDPOINT: Final[str] = "coding_plan/vlm"
GATEWAY_WHISPER_MODEL: Final[str] = "small"


def provider_default_model(provider: str) -> str:
    """Default chat model id for a provider name (L0 registry lookup)."""
    key = str(provider or "").strip().lower()
    return PROVIDER_ENV_DEFAULT_MODEL.get(key, "")
