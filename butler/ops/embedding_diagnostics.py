"""Compact embedding / semantic memory lines for doctor and /诊断."""

from __future__ import annotations

from typing import Any

from butler.memory.semantic_config import (
    embedding_model_name,
    embedding_provider_name,
    semantic_memory_enabled,
)


def collect_embedding_snapshot(*, vector_rows: int = 0) -> dict[str, Any]:
    """Build embedding status dict for diagnostics."""
    provider = embedding_provider_name()
    model = embedding_model_name()
    semantic_on = semantic_memory_enabled()
    out: dict[str, Any] = {
        "embedding_provider": provider,
        "embedding_model": model,
        "semantic_enabled": semantic_on,
        "vector_rows": int(vector_rows or 0),
        "embedding_degraded": False,
        "embedding_recommend_fastembed": False,
    }
    prov = (provider or "").strip().lower()
    if prov in ("local", "") and model in ("hashing-v1", ""):
        out["embedding_recommend_fastembed"] = True
    try:
        from butler.memory.embedding import HashingEmbedder, get_embedder

        emb = get_embedder()
        out["embedding_degraded"] = bool(getattr(emb, "degraded", False))
        if isinstance(emb, HashingEmbedder) and prov not in ("local", ""):
            out["embedding_degraded"] = True
    except Exception:
        pass
    return out


def format_embedding_status_line(snapshot: dict[str, Any] | None = None) -> str:
    """One-line summary: 语义记忆 + provider/model + vector count."""
    snap = snapshot or collect_embedding_snapshot()
    sem = "开" if snap.get("semantic_enabled") else "关"
    prov = snap.get("embedding_provider") or "?"
    model = snap.get("embedding_model") or "?"
    rows = int(snap.get("vector_rows") or 0)
    parts = [f"语义记忆: {sem}", f"嵌入: {prov}/{model}"]
    if snap.get("semantic_enabled"):
        parts.append(f"向量 {rows} 条")
    if snap.get("embedding_degraded"):
        parts.append("⚠ 已降级 hashing")
    elif snap.get("embedding_recommend_fastembed"):
        parts.append("建议 fastembed+BGE（见 .env.example）")
    return " · ".join(parts)


def format_embedding_doctor_lines() -> list[str]:
    """Multi-line block for butler doctor."""
    snap = collect_embedding_snapshot()
    lines = [
        f"  Embedding 档位: {snap.get('embedding_provider')}/{snap.get('embedding_model')}",
        f"  BUTLER_SEMANTIC_MEMORY: {'1' if snap.get('semantic_enabled') else '0'}",
    ]
    if snap.get("embedding_degraded"):
        lines.append("  ⚠ 嵌入已降级为 HashingEmbedder（召回质量下降）")
    elif snap.get("embedding_recommend_fastembed"):
        lines.append(
            "  ⚠ 当前为 local/hashing-v1；生产推荐 "
            "BUTLER_EMBEDDING_PROVIDER=fastembed + BAAI/bge-small-en-v1.5"
        )
    return lines


__all__ = [
    "collect_embedding_snapshot",
    "format_embedding_doctor_lines",
    "format_embedding_status_line",
]
