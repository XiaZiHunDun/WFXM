"""Embedding backends for Butler semantic memory (P0: local hashing, no network)."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

from butler.memory.semantic_config import embedding_model_name, embedding_provider_name

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

_JIEBA = None
_JIEBA_TRIED = False


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


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))


def get_embedder() -> Embedder:
    """Resolve embedder from env. P0 only implements ``local`` (hashing)."""
    provider = embedding_provider_name()
    model = embedding_model_name()
    if provider in ("local", "hash", "hashing", ""):
        return HashingEmbedder(model_id=model or "hashing-v1")
    logger.warning(
        "Embedding provider %r not implemented yet; falling back to local hashing",
        provider,
    )
    return HashingEmbedder(model_id="hashing-v1")
