"""Best-effort embedding probe helpers (P0-A)."""

from __future__ import annotations

from typing import cast

from butler.core.best_effort import safe_best_effort


def probe_embedder_snapshot() -> dict[str, bool] | None:
    def _run() -> dict[str, bool]:
        from butler.memory.embedding import HashingEmbedder, get_embedder

        emb = get_embedder()
        degraded = bool(getattr(emb, "degraded", False))
        from butler.memory.semantic_config import embedding_provider_name

        prov = (embedding_provider_name() or "").strip().lower()
        if isinstance(emb, HashingEmbedder) and prov not in ("local", ""):
            degraded = True
        return {"embedding_degraded": degraded}

    result = safe_best_effort(
        _run,
        label="embedding_diagnostics.probe",
        default=None,
    )
    return result if isinstance(result, dict) else None
