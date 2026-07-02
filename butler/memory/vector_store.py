"""ChromaDB vector store abstraction (optional, **not on production recall path**).

Production semantic recall uses ``SemanticMemoryIndex`` (sqlite ``memory_vectors.db``
+ hybrid FTS) via ``butler/memory/semantic_index.py``. ``get_vector_store()`` here
is for tests, doctor probes, and future experiments only — no gateway/loop caller
indexes experiences through this module today.

Falls back to in-memory brute-force search when ChromaDB is not installed.
"""

from __future__ import annotations

import logging

from butler.memory.vector_store_ops import (
    chroma_delete,
    chroma_query,
    init_vector_store,
    load_fallback_docs,
)
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class VectorStore(Protocol):
    """Minimal vector store interface."""

    def add(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        ...

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def delete(self, doc_id: str) -> bool:
        ...

    def count(self) -> int:
        ...


def _store_root() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "vector_store"


def _get_embedder():
    from butler.memory.embedding import get_embedder

    return get_embedder()


class ChromaVectorStore:
    """ChromaDB-backed persistent vector store."""

    def __init__(self, collection_name: str = "butler_personal") -> None:
        import chromadb  # type: ignore[import-untyped]

        persist_dir = str(_store_root() / "chroma")
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = _get_embedder()

    def add(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        meta = dict(metadata or {})
        meta.setdefault("created_ts", time.time())
        meta["text_hash"] = hashlib.md5(text.encode()).hexdigest()[:12]

        for k, v in list(meta.items()):
            if v is None:
                del meta[k]
            elif not isinstance(v, (str, int, float, bool)):
                meta[k] = str(v)

        embedding = self._embedder.embed(text)
        self._collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[meta],
        )

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        embedding = self._embedder.embed(text)
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(top_k, self._collection.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        results = chroma_query(self._collection, kwargs)
        if results is None:
            return []

        hits: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        for i, doc_id in enumerate(ids):
            hits.append({
                "id": doc_id,
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "score": round(1.0 - (dists[i] if i < len(dists) else 1.0), 4),
            })
        return hits

    def delete(self, doc_id: str) -> bool:
        return chroma_delete(self._collection, doc_id)

    def count(self) -> int:
        return self._collection.count()


class InMemoryVectorStore:
    """Brute-force fallback when ChromaDB is not installed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._docs: dict[str, dict[str, Any]] = {}
        self._embedder = _get_embedder()
        self._persist_path = _store_root() / "fallback.jsonl"
        self._load_persisted()

    def _load_persisted(self) -> None:
        for entry in load_fallback_docs(self._persist_path):
            self._docs[entry["id"]] = entry

    def _persist(self) -> None:
        import json

        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(doc, ensure_ascii=False) for doc in self._docs.values()]
        self._persist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def add(
        self,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        embedding = self._embedder.embed(text)
        with self._lock:
            self._docs[doc_id] = {
                "id": doc_id,
                "text": text,
                "metadata": dict(metadata or {}),
                "embedding": embedding,
                "created_ts": time.time(),
            }
            self._persist()

    def query(
        self,
        text: str,
        *,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        from butler.memory.embedding import cosine_similarity

        with self._lock:
            if not self._docs:
                return []
            snapshot = list(self._docs.values())
        query_vec = self._embedder.embed(text)
        scored: list[tuple[float, dict[str, Any]]] = []
        for doc in snapshot:
            if where:
                meta = doc.get("metadata", {})
                if not all(meta.get(k) == v for k, v in where.items()):
                    continue
            sim = cosine_similarity(query_vec, doc.get("embedding", []))
            scored.append((sim, doc))
        scored.sort(key=lambda x: -x[0])
        return [
            {
                "id": d["id"],
                "text": d["text"],
                "metadata": d.get("metadata", {}),
                "score": round(s, 4),
            }
            for s, d in scored[:top_k]
        ]

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id in self._docs:
                del self._docs[doc_id]
                self._persist()
                return True
            return False

    def count(self) -> int:
        with self._lock:
            return len(self._docs)


_STORE_CACHE: dict[str, VectorStore] = {}
_STORE_CACHE_MAX = 64
_STORE_CACHE_LOCK = threading.Lock()


def get_vector_store(collection: str = "butler_personal") -> VectorStore:
    """Get or create a vector store instance (ChromaDB preferred, fallback to in-memory)."""
    with _STORE_CACHE_LOCK:
        cached = _STORE_CACHE.get(collection)
        if cached is not None:
            return cached

    store: VectorStore
    store = init_vector_store(
        collection=collection,
        chroma_factory=lambda: ChromaVectorStore(collection_name=collection),
        fallback_factory=InMemoryVectorStore,
        on_chroma=lambda c: logger.info(
            "Using ChromaDB vector store (collection=%s)", c
        ),
        on_import_error=lambda: logger.info(
            "ChromaDB not installed; using in-memory fallback vector store"
        ),
        on_fallback=lambda: None,
    )

    with _STORE_CACHE_LOCK:
        existing = _STORE_CACHE.get(collection)
        if existing is not None:
            return existing
        if len(_STORE_CACHE) >= _STORE_CACHE_MAX:
            oldest = next(iter(_STORE_CACHE))
            _STORE_CACHE.pop(oldest, None)
            logger.info("Evicted vector store cache entry: %s", oldest)
        _STORE_CACHE[collection] = store
    return store


def chroma_data_present_hint(butler_home: Path | None = None) -> str:
    """Return a doctor hint when legacy Chroma data exists but semantic memory is off."""
    from butler.memory.semantic_config import semantic_memory_enabled

    if semantic_memory_enabled():
        return ""
    root = Path(butler_home).expanduser() if butler_home is not None else _store_root().parent
    chroma_dir = root / "vector_store" / "chroma"
    fallback = root / "vector_store" / "fallback.jsonl"
    if chroma_dir.is_dir() and any(chroma_dir.iterdir()):
        return (
            "检测到 Chroma 实验数据（非生产链）；语义检索请用 memory_vectors.db + "
            "BUTLER_SEMANTIC_MEMORY=1"
        )
    if fallback.is_file() and fallback.stat().st_size > 0:
        return "检测到 vector_store/fallback.jsonl（实验链）；生产请用 SemanticMemoryIndex"
    return ""
