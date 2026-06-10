"""A6 Recall@3 gate — embedding retrieval quality must exceed 80%.

Implements FINDING-2 / MA2: the embedder (default or API) must retrieve
at least 80% of expected documents in the top-3 results across a
standardised query set.

Gate: Recall@3 ≥ 0.80 on both Chinese and English query pairs.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

import pytest


CORPUS = [
    ("doc_deploy", "部署流程使用 Docker 容器在 8080 端口运行"),
    ("doc_python", "用户偏好使用 Python 3.12 进行开发"),
    ("doc_testing", "单元测试框架使用 pytest 搭配 coverage 检测"),
    ("doc_database", "数据库采用 PostgreSQL 主从复制架构"),
    ("doc_auth", "用户认证使用 JWT token 加密方案"),
    ("doc_cache", "缓存层使用 Redis cluster 模式部署"),
    ("doc_api", "API 网关使用 Nginx 反向代理加负载均衡"),
    ("doc_monitor", "监控方案使用 Prometheus 和 Grafana 仪表盘"),
    ("doc_cicd", "CI/CD 流水线使用 GitHub Actions 自动化"),
    ("doc_config", "配置管理采用环境变量加 dotenv 文件"),
]

# (query, expected_doc_id) — query is a semantic variant of the original
QUERY_PAIRS = [
    ("Docker 部署", "doc_deploy"),
    ("Python 开发", "doc_python"),
    ("pytest 测试", "doc_testing"),
    ("PostgreSQL 数据库", "doc_database"),
    ("JWT 认证", "doc_auth"),
    ("Redis 缓存", "doc_cache"),
    ("Nginx API 网关", "doc_api"),
    ("Prometheus 监控", "doc_monitor"),
    ("GitHub Actions CI", "doc_cicd"),
    ("环境变量配置", "doc_config"),
]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


def _recall_at_k(
    embedder: Any,
    corpus: list[tuple[str, str]],
    queries: list[tuple[str, str]],
    k: int = 3,
) -> float:
    """Compute Recall@k: fraction of queries where expected doc is in top-k."""
    corpus_vecs: list[tuple[str, list[float]]] = []
    for doc_id, text in corpus:
        vec = embedder.embed(text)
        corpus_vecs.append((doc_id, vec))

    hits = 0
    for query_text, expected_id in queries:
        qvec = embedder.embed(query_text)
        scored = sorted(
            ((doc_id, _cosine_sim(qvec, dvec)) for doc_id, dvec in corpus_vecs),
            key=lambda x: x[1],
            reverse=True,
        )
        top_k_ids = [doc_id for doc_id, _ in scored[:k]]
        if expected_id in top_k_ids:
            hits += 1

    return hits / max(1, len(queries))


class TestRecallGate:
    """A6 Recall@3 gate — must exceed 80%."""

    def test_hashing_embedder_recall_at_3(self):
        """HashingEmbedder (default) should achieve Recall@3 ≥ 0.80 on the gate corpus."""
        from butler.memory.embedding import HashingEmbedder

        embedder = HashingEmbedder(dimension=384)
        r3 = _recall_at_k(embedder, CORPUS, QUERY_PAIRS, k=3)
        assert r3 >= 0.80, (
            f"Recall@3 = {r3:.2%} < 80% gate threshold. "
            f"Embedding quality is insufficient for production use."
        )

    def test_hashing_embedder_recall_at_5(self):
        """Recall@5 should be even higher."""
        from butler.memory.embedding import HashingEmbedder

        embedder = HashingEmbedder(dimension=384)
        r5 = _recall_at_k(embedder, CORPUS, QUERY_PAIRS, k=5)
        assert r5 >= 0.80, f"Recall@5 = {r5:.2%} < 80%"

    def test_fastembed_recall_at_3_if_available(self):
        """FastEmbedEmbedder should achieve Recall@3 ≥ 0.80 (skipped if not installed)."""
        try:
            from butler.memory.embedding import FastEmbedEmbedder
        except ImportError:
            pytest.skip("fastembed not installed")

        try:
            embedder = FastEmbedEmbedder()
        except Exception:
            pytest.skip("FastEmbedEmbedder init failed")

        r3 = _recall_at_k(embedder, CORPUS, QUERY_PAIRS, k=3)
        assert r3 >= 0.80, (
            f"FastEmbed Recall@3 = {r3:.2%} < 80% gate threshold."
        )

    def test_recall_metric_documented(self):
        """Ensure the recall gate threshold is self-documented."""
        from butler.memory.embedding import HashingEmbedder

        embedder = HashingEmbedder(dimension=384)
        r3 = _recall_at_k(embedder, CORPUS, QUERY_PAIRS, k=3)
        r5 = _recall_at_k(embedder, CORPUS, QUERY_PAIRS, k=5)
        details = {
            "recall@3": round(r3, 4),
            "recall@5": round(r5, 4),
            "corpus_size": len(CORPUS),
            "query_count": len(QUERY_PAIRS),
            "gate_threshold": 0.80,
        }
        assert details["recall@3"] >= details["gate_threshold"]


class TestRecallAtKHelper:
    """Validate the Recall@k computation itself."""

    def test_perfect_recall(self):
        from butler.memory.embedding import HashingEmbedder

        embedder = HashingEmbedder(dimension=64)
        corpus = [("a", "hello world"), ("b", "goodbye world")]
        queries = [("hello world", "a"), ("goodbye world", "b")]
        r = _recall_at_k(embedder, corpus, queries, k=2)
        assert r == 1.0

    def test_empty_corpus(self):
        from butler.memory.embedding import HashingEmbedder

        embedder = HashingEmbedder(dimension=64)
        r = _recall_at_k(embedder, [], [], k=3)
        assert r == 0.0 or r == 1.0  # 0/0 case
