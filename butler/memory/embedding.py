"""Embedding backends for Butler semantic memory (local + optional API)."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from typing import Any, Protocol

from butler.memory.semantic_config import embedding_model_name, embedding_provider_name

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

_JIEBA = None
_JIEBA_TRIED = False

_DEFAULT_OPENAI_MODEL = "text-embedding-3-small"
_DEFAULT_MINIMAX_MODEL = "embo-01"


def _tokenize(text: str) -> list[str]:
    global _JIEBA, _JIEBA_TRIED
    if not _JIEBA_TRIED:
        _JIEBA_TRIED = True
        try:
            import jieba

            jieba.setLogLevel(logging.WARNING)
            _JIEBA = jieba
        except ImportError:
            _JIEBA = None
    raw = (text or "").strip().lower()
    if not raw:
        return []
    if _JIEBA is not None:
        return [t.strip() for t in _JIEBA.lcut(raw) if t.strip()]
    return [m.group(0) for m in _TOKEN_RE.finditer(raw)]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 1e-12:
        return vec
    return [x / norm for x in vec]


class Embedder(Protocol):
    @property
    def model_id(self) -> str:
        ...

    @property
    def dimension(self) -> int:
        ...

    def embed(self, text: str) -> list[float]:
        ...


class HashingEmbedder:
    """Deterministic character/token hashing embedder — offline, good for tests and P0."""

    def __init__(self, *, dimension: int = 96, model_id: str = "hashing-v1") -> None:
        self._dim = max(8, int(dimension))
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        tokens = _tokenize(text)
        if not tokens:
            return vec
        for tok in tokens:
            digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            h = int.from_bytes(digest, "little")
            idx = h % self._dim
            sign = 1.0 if (h >> 8) & 1 else -1.0
            vec[idx] += sign
        return _l2_normalize(vec)


class OpenAIEmbedder:
    """OpenAI-compatible embeddings API (OpenAI, DeepSeek-compatible gateways)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dim = 0
        self._model_id = f"openai/{model}"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dim or 1536

    def embed(self, text: str) -> list[float]:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        resp = client.embeddings.create(model=self._model, input=(text or "").strip())
        vec = list(resp.data[0].embedding)
        self._dim = len(vec)
        return _l2_normalize(vec)


class MinimaxEmbedder:
    """MiniMax OpenAI-compatible embeddings endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.minimax.chat/v1",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dim = 0
        self._model_id = f"minimax/{model}"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dim or 1024

    def embed(self, text: str) -> list[float]:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        resp = client.embeddings.create(model=self._model, input=(text or "").strip())
        vec = list(resp.data[0].embedding)
        self._dim = len(vec)
        return _l2_normalize(vec)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))


class FastEmbedEmbedder:
    """Local ONNX-based embeddings via fastembed (no PyTorch required)."""

    _DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    _DEFAULT_DIM = 384

    def __init__(self, *, model_name: str = "") -> None:
        self._model_name = model_name or self._DEFAULT_MODEL
        self._dim = self._DEFAULT_DIM
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding  # type: ignore[import-untyped]

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    @property
    def model_id(self) -> str:
        return f"fastembed/{self._model_name}"

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        model = self._ensure_model()
        results = list(model.embed([text.strip() or "."]))
        vec = [float(x) for x in results[0]]
        self._dim = len(vec)
        return _l2_normalize(vec)


def _resolve_api_embedder(provider: str, model: str) -> Embedder | None:
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            logger.warning("BUTLER_EMBEDDING_PROVIDER=openai but OPENAI_API_KEY unset")
            return None
        m = model if model and model != "hashing-v1" else _DEFAULT_OPENAI_MODEL
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        return OpenAIEmbedder(api_key=key, model=m, base_url=base)

    if provider == "minimax":
        key = os.getenv("MINIMAX_API_KEY", "").strip()
        if not key:
            logger.warning("BUTLER_EMBEDDING_PROVIDER=minimax but MINIMAX_API_KEY unset")
            return None
        m = model if model and model != "hashing-v1" else _DEFAULT_MINIMAX_MODEL
        base = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1").strip()
        return MinimaxEmbedder(api_key=key, model=m, base_url=base)

    return None


def _resolve_fastembed(model: str) -> Embedder | None:
    """Try to instantiate a fastembed embedder; return None if library unavailable."""
    try:
        m = model if model and model != "hashing-v1" else FastEmbedEmbedder._DEFAULT_MODEL
        embedder = FastEmbedEmbedder(model_name=m)
        probe = embedder.embed("ping")
        if probe:
            return embedder
    except ImportError:
        logger.warning(
            "BUTLER_EMBEDDING_PROVIDER=fastembed but fastembed not installed; "
            "pip install 'butler-system[embeddings]'"
        )
    except Exception as exc:
        logger.warning("fastembed init failed (%s); falling back to local hashing", exc)
    return None


def get_embedder() -> Embedder:
    """Resolve embedder from env; API providers fall back to local hashing on failure."""
    provider = embedding_provider_name()
    model = embedding_model_name()
    if provider in ("local", "hash", "hashing", ""):
        logger.debug("Embedding provider: local HashingEmbedder (%s)", model or "hashing-v1")
        return HashingEmbedder(model_id=model or "hashing-v1")

    if provider == "fastembed":
        fe = _resolve_fastembed(model)
        if fe is not None:
            logger.info("Embedding provider: fastembed (%s)", fe.model_id)
            return fe
        logger.warning("fastembed unavailable → fallback to local HashingEmbedder")
        return HashingEmbedder(model_id="hashing-v1")

    api = _resolve_api_embedder(provider, model)
    if api is not None:
        try:
            probe = api.embed("ping")
            if probe:
                logger.info("Embedding provider: %s (%s)", provider, api.model_id)
                return api
        except Exception as exc:
            logger.warning(
                "Embedding provider %r probe failed (%s) → fallback to HashingEmbedder",
                provider,
                exc,
            )
    else:
        logger.warning(
            "Embedding provider %r unavailable (missing API key?) → fallback to HashingEmbedder",
            provider,
        )
    return HashingEmbedder(model_id="hashing-v1")
