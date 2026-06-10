"""Embedding provider health check — Recall@3 smoke for production deploy."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from butler.memory.embedding import HashingEmbedder, get_embedder
from butler.memory.semantic_config import embedding_model_name, embedding_provider_name
from butler.memory.semantic_index import SemanticMemoryIndex

_GT_ENTRIES = [
    ("Python 测试", "gt-2"),
    ("部署检查门检", "gt-3"),
    ("微信消息网关", "gt-4"),
    ("记忆向量检索", "gt-5"),
    ("定时任务报告", "gt-7"),
]

_SEED = [
    ("gt-1", "用户喜欢在早上9点开始工作"),
    ("gt-2", "项目使用 Python 3.13 和 pytest 进行测试"),
    ("gt-3", "部署流程需要先运行五报告门检"),
    ("gt-4", "微信消息处理通过 Gateway 入站管线"),
    ("gt-5", "记忆系统支持向量检索和全文检索混合排序"),
    ("gt-6", "工作流需要人工确认才能执行危险步骤"),
    ("gt-7", "Butler 管家每天会自动执行定时任务报告"),
    ("gt-8", "上下文压缩使用辅助模型生成摘要"),
]


@dataclass
class EmbeddingHealthReport:
    provider: str
    model: str
    recall_at_3: float
    hits: int
    total: int
    degraded: bool
    message: str

    def ok(self, *, min_recall: float = 0.8) -> bool:
        if self.degraded:
            return False
        return self.recall_at_3 >= min_recall


def check_embedding_recall(*, k: int = 3, min_recall: float = 0.8) -> EmbeddingHealthReport:
    """Run a lightweight Recall@K smoke against the configured embedder."""
    provider = embedding_provider_name()
    model = embedding_model_name()
    embedder = get_embedder()
    degraded = isinstance(embedder, HashingEmbedder) and provider not in ("local", "")

    with tempfile.TemporaryDirectory() as tmpdir:
        idx = SemanticMemoryIndex(Path(tmpdir) / "health.db", embedder=embedder)
        try:
            for sid, content in _SEED:
                idx.upsert(source="experience", source_id=sid, content=content, category="health")
            hits = 0
            for query, expected_id in _GT_ENTRIES:
                results = idx.search(query, limit=k)
                if any(r.get("source_id") == expected_id for r in results):
                    hits += 1
            total = len(_GT_ENTRIES)
            recall = hits / total if total else 0.0
        finally:
            idx.close()

    if degraded:
        msg = f"provider={provider} degraded to HashingEmbedder (Recall@3={recall:.0%})"
    elif recall >= min_recall:
        msg = f"Recall@3={recall:.0%} >= {min_recall:.0%}"
    else:
        msg = f"Recall@3={recall:.0%} < {min_recall:.0%} threshold"

    return EmbeddingHealthReport(
        provider=provider,
        model=model,
        recall_at_3=recall,
        hits=hits,
        total=total,
        degraded=degraded,
        message=msg,
    )


__all__ = ["EmbeddingHealthReport", "check_embedding_recall"]
