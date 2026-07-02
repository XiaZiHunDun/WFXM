"""Best-effort helpers for onboard reporting (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def append_embedding_recommendation_lines(lines: list[str]) -> None:
    def _run() -> None:
        from butler.ops.embedding_diagnostics import collect_embedding_snapshot

        snap = collect_embedding_snapshot()
        if snap.get("embedding_recommend_fastembed"):
            lines.append("")
            lines.append("记忆推荐（gateway）")
            lines.append(
                "  ⚠ 嵌入为 local/hashing-v1；建议 BUTLER_EMBEDDING_PROVIDER=fastembed "
                "+ BUTLER_SEMANTIC_MEMORY=1（见 .env.example）"
            )

    safe_best_effort(_run, label="onboard.embedding_recommend", default=None)
