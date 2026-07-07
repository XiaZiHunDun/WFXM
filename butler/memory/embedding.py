"""Embedding backends for Butler semantic memory (local + optional API)."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import threading
from typing import Any, Protocol, cast

from butler.memory.semantic_config import embedding_model_name, embedding_provider_name
from butler.defaults.model_defaults import DEFAULT_EMBEDDING_MODEL
from butler.defaults.model_defaults import DEFAULT_EMBEDDING_MODEL, MINIMAX_EMBEDDING_MODEL, OPENAI_EMBEDDING_MODEL, QWEN_EMBEDDING_MODEL
from butler.memory.embedding_ops import resolve_fastembed_loud
from butler.memory.embedding_ops import register_embedding_degradation_safe
from butler.memory.embedding_ops import clear_embedding_degradation_safe
from butler.memory.embedding_ops import clear_embedding_degradation_safe, probe_api_embedder_loud

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

_JIEBA = None
_JIEBA_TRIED = False
_JIEBA_LOCK = threading.Lock()


def _tokenize(text: str) -> list[str]:
    global _JIEBA, _JIEBA_TRIED
    if not _JIEBA_TRIED:
        with _JIEBA_LOCK:
            if not _JIEBA_TRIED:
                _JIEBA_TRIED = True
                try:
                    import jieba  # type: ignore[import-untyped]

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
    # Audit R2-3: True iff the embedder was instantiated through a fallback
    # path (fastembed init / API key / probe failure). Used by /诊断 to surface
    # recall-quality collapse instead of silently degrading to local hashing.
    degraded: bool

    @property
    def model_id(self) -> str:
        ...

    @property
    def dimension(self) -> int:
        ...

    def embed(self, text: str) -> list[float]:
        ...

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingEmbedder:
    """Deterministic character/token hashing embedder — offline, good for tests and P0."""

    def __init__(
        self,
        *,
        dimension: int = 96,
        model_id: str | None = None,
        degraded: bool = False,
        requested_provider: str = "",
        requested_model: str = "",
    ) -> None:

        self._dim = max(8, int(dimension))
        self._model_id = model_id or DEFAULT_EMBEDDING_MODEL
        # Audit R2-3: degraded=True marks fallback instances created when the
        # configured embedding provider failed. requested_provider/model preserve
        # what the user actually asked for so /诊断 can surface the gap.
        self.degraded = bool(degraded)
        self.requested_provider = str(requested_provider or "")
        self.requested_model = str(requested_model or "")

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

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class OpenAIEmbedder:
    """OpenAI-compatible embeddings API (OpenAI, DeepSeek-compatible gateways)."""

    # Audit R2-3: real (non-fallback) providers are not degraded.
    degraded: bool = False

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
        self._client = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dim or 1536

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def embed(self, text: str) -> list[float]:
        client = self._get_client()
        resp = client.embeddings.create(model=self._model, input=(text or "").strip())
        vec = list(resp.data[0].embedding)
        self._dim = len(vec)
        return _l2_normalize(vec)

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        inputs = [(t or "").strip() for t in texts]
        resp = client.embeddings.create(model=self._model, input=inputs)
        vecs: list[list[float]] = []
        for item in sorted(resp.data, key=lambda d: d.index):
            vec = list(item.embedding)
            self._dim = len(vec)
            vecs.append(_l2_normalize(vec))
        return vecs


class MinimaxEmbedder:
    """MiniMax OpenAI-compatible embeddings endpoint."""

    # Audit R2-3: real (non-fallback) providers are not degraded.
    degraded: bool = False

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
        self._client = None

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dim or 1024

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def embed(self, text: str) -> list[float]:
        client = self._get_client()
        resp = client.embeddings.create(model=self._model, input=(text or "").strip())
        vec = list(resp.data[0].embedding)
        self._dim = len(vec)
        return _l2_normalize(vec)

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        inputs = [(t or "").strip() for t in texts]
        resp = client.embeddings.create(model=self._model, input=inputs)
        vecs: list[list[float]] = []
        for item in sorted(resp.data, key=lambda d: d.index):
            vec = list(item.embedding)
            self._dim = len(vec)
            vecs.append(_l2_normalize(vec))
        return vecs


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))


class FastEmbedEmbedder:
    """Local ONNX-based embeddings via fastembed (no PyTorch required)."""

    _DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    _DEFAULT_DIM = 384

    # Audit R2-3: real (non-fallback) providers are not degraded.
    degraded: bool = False

    def __init__(self, *, model_name: str = "") -> None:
        self._model_name = model_name or self._DEFAULT_MODEL
        self._dim = self._DEFAULT_DIM
        self._model: Any = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

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

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure_model()
        inputs = [t.strip() or "." for t in texts]
        vecs: list[list[float]] = []
        for result in model.embed(inputs):
            vec = [float(x) for x in result]
            self._dim = len(vec)
            vecs.append(_l2_normalize(vec))
        return vecs


def _resolve_api_embedder(provider: str, model: str) -> Embedder | None:

    fallback = DEFAULT_EMBEDDING_MODEL
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            # Audit R2-3: missing API key collapses recall to local hashing.
            logger.error("BUTLER_EMBEDDING_PROVIDER=openai but OPENAI_API_KEY unset")
            return None
        m = model if model and model != fallback else OPENAI_EMBEDDING_MODEL
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        return OpenAIEmbedder(api_key=key, model=m, base_url=base)

    if provider == "minimax":
        key = os.getenv("MINIMAX_API_KEY", "").strip()
        if not key:
            logger.error("BUTLER_EMBEDDING_PROVIDER=minimax but MINIMAX_API_KEY unset")
            return None
        m = model if model and model != fallback else MINIMAX_EMBEDDING_MODEL
        base = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1").strip()
        return MinimaxEmbedder(api_key=key, model=m, base_url=base)

    if provider in ("dashscope", "qwen", "tongyi"):
        key = os.getenv("DASHSCOPE_API_KEY", os.getenv("QWEN_API_KEY", "")).strip()
        if not key:
            logger.error("BUTLER_EMBEDDING_PROVIDER=%s but DASHSCOPE_API_KEY unset",
                         provider)
            return None
        m = model if model and model != fallback else QWEN_EMBEDDING_MODEL
        base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        return OpenAIEmbedder(api_key=key, model=m, base_url=base)

    return None


def _resolve_fastembed(model: str) -> Embedder | None:

    return cast(Embedder | None, resolve_fastembed_loud(model))


import functools
from collections import OrderedDict


_EMBED_CACHE_DEFAULT_MAX = 128


def _embed_cache_key(text: str) -> str:
    """Stable cache key for embedder query (Sprint 13 PERF-13-2).

    blake2b 是稳定的（不依赖 PYTHONHASHSEED）。
    """
    return hashlib.blake2b((text or "").encode("utf-8")).hexdigest()[:16]


class _CachedEmbedder:
    """LRU wrapper around an embedder (Sprint 13 PERF-13-2).

    对 API/本地模型 embedder 包装一层 query 缓存，避免同一文本重复
    触发昂贵的 API 调用。HashingEmbedder 不包装（本身无开销）。
    """

    def __init__(self, inner: Embedder, *, max_size: int = _EMBED_CACHE_DEFAULT_MAX) -> None:
        self._inner = inner
        self._max_size = max(1, int(max_size))
        self._cache: "OrderedDict[str, list[float]]" = OrderedDict()

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    @property
    def degraded(self) -> bool:
        # Audit R2-3: proxy degraded flag so /诊断 can detect a wrapped
        # fallback embedder (in practice we don't wrap HashingEmbedder, but the
        # contract must be respected for any future Embedder).
        return bool(getattr(self._inner, "degraded", False))

    def embed(self, text: str) -> list[float]:
        key = _embed_cache_key(text)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        vec = self._inner.embed(text)
        self._cache[key] = vec
        self._cache.move_to_end(key)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        return vec

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float] | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []
        for i, text in enumerate(texts):
            key = _embed_cache_key(text)
            if key in self._cache:
                self._cache.move_to_end(key)
                results[i] = self._cache[key]
            else:
                miss_indices.append(i)
                miss_texts.append(text)
        if miss_texts:
            new_vecs = self._inner.batch_embed(miss_texts)
            for idx, text, vec in zip(miss_indices, miss_texts, new_vecs):
                key = _embed_cache_key(text)
                self._cache[key] = vec
                self._cache.move_to_end(key)
                results[idx] = vec
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
        return [vec for vec in results if vec is not None]


@functools.lru_cache(maxsize=4)
def _cached_embedder(provider: str, model: str) -> Embedder:
    """Cached embedder resolution keyed by (provider, model)."""
    return _build_embedder(provider, model)


def get_embedder() -> Embedder:
    """Resolve embedder from env; API providers fall back to local hashing on failure."""
    provider = embedding_provider_name()
    model = embedding_model_name()
    return _cached_embedder(provider, model)


def _build_embedder(provider: str, model: str) -> Embedder:
    raw = _build_raw_embedder(provider, model)
    # PERF-13-2: 包装 query 缓存（HashingEmbedder 无 API 开销，跳过）
    if isinstance(raw, HashingEmbedder):
        return raw
    return cast(Embedder, _CachedEmbedder(raw))


def _degraded_hashing(provider: str, model: str) -> "HashingEmbedder":
    """Build a fallback HashingEmbedder tagged with the requested provider/model.

    Audit R2-3: every fallback embedder must carry `degraded=True` plus the
    user-requested provider/model so /诊断 can surface the gap (e.g.
    requested openai embedding → local hashing fallback).
    """

    register_embedding_degradation_safe(provider=provider, model=model)

    return HashingEmbedder(
        model_id=DEFAULT_EMBEDDING_MODEL,
        degraded=True,
        requested_provider=provider or "",
        requested_model=model or "",
    )


def _build_raw_embedder(provider: str, model: str) -> Embedder:

    if provider in ("local", "hash", "hashing", ""):
        mid = model or DEFAULT_EMBEDDING_MODEL
        logger.debug("Embedding provider: local HashingEmbedder (%s)", mid)
        return HashingEmbedder(model_id=mid)

    if provider == "fastembed":
        fe = _resolve_fastembed(model)
        if fe is not None:
            logger.info("Embedding provider: fastembed (%s)", fe.model_id)

            clear_embedding_degradation_safe()
            return fe
        # Audit R2-3: escalate to ERROR — recall quality is collapsing.
        logger.error(
            "fastembed unavailable → fallback to local HashingEmbedder "
            "(requested fastembed/%s)",
            model or "default",
        )
        return _degraded_hashing("fastembed", model)

    api = _resolve_api_embedder(provider, model)
    if api is not None:

        probed = probe_api_embedder_loud(api, provider=provider)
        if probed is not None:
            logger.info("Embedding provider: %s (%s)", provider, probed.model_id)
            clear_embedding_degradation_safe()
            return cast(Embedder, probed)
    else:
        # Audit R2-3: missing API key / unsupported provider → degraded.
        logger.error(
            "Embedding provider %r unavailable (missing API key?) → fallback to HashingEmbedder",
            provider,
        )
    return _degraded_hashing(provider, model)
