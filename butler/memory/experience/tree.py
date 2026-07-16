"""ExperienceTree — the 2-layer management system's core entry point.

Layer 1: Domain routing → identify which experience domain is relevant
Layer 2: Category retrieval → search within domain's categories

Usage:
    tree = ExperienceTree()
    hits = tree.retrieve("How to use FastAPI for auth?")  # → experience hits
    node_id = tree.write("Query", "Result", {"tool_name": "..."})  # → write new exp
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from butler.memory.experience.domain_router import DomainRouter
from butler.memory.experience.retriever import ExperienceRetriever
from butler.memory.experience.store import ExperienceHit, ExperienceNode, ExperienceStore
from butler.memory.experience.writer import ExperienceWriter
from butler.memory.experience.taxonomy import DOMAINS, CATEGORIES, get_domain_name, get_category_name

logger = logging.getLogger(__name__)


class ExperienceTree:
    """2-layer experience-knowledge tree.

    retrieve(): Layer 1 (domain route) → Layer 2 (category retrieve)
    write(): classify → store → index in all backends
    """

    def __init__(self, store: ExperienceStore | None = None):
        self._store = store or ExperienceStore()
        self._router = DomainRouter(self._store)
        self._retriever = ExperienceRetriever(self._store)
        self._writer = ExperienceWriter(self._store)

    # ─── retrieve ───

    def retrieve(self, query: str, top_k: int = 5) -> list[ExperienceHit]:
        """Retrieve relevant experiences for a query.

        Flow:
        1. DomainRouter.route(query) → (domain_id, confidence)
        2. If confidence >= 0.15: ExperienceRetriever.retrieve(domain, query)
        3. If confidence < 0.15: search across all domains via FTS
        """
        domain_id, confidence = self._router.route(query)
        logger.debug("Domain routed to '%s' (confidence=%.3f)", domain_id, confidence)

        if confidence >= 0.10:
            hits = self._retriever.retrieve(domain_id, query, top_k=top_k)
            if hits:
                self._router.record_hit(domain_id)
                for hit in hits:
                    self._store.increment_hit(hit.node.node_id, success=True)
                return hits

            all_hits = self._search_all_domains(query, top_k)
            if all_hits:
                return all_hits

        fts_hits = self._search_fts_all(query, top_k)
        if fts_hits:
            return fts_hits

        return self._get_popular(top_k)

    def _search_all_domains(self, query: str, top_k: int) -> list[ExperienceHit]:
        candidates = self._router.route_multi(query, top_n=3)
        all_hits: list[ExperienceHit] = []
        for domain_id, _ in candidates:
            hits = self._retriever.retrieve(domain_id, query, top_k=top_k)
            all_hits.extend(hits)
        all_hits.sort(key=lambda h: h.score, reverse=True)
        return all_hits[:top_k]

    def _search_fts_all(self, query: str, top_k: int) -> list[ExperienceHit]:
        nodes = self._store.search_fts(query, limit=top_k)
        return [
            ExperienceHit(node=n, score=0.5 + min(n.hit_count * 0.01, 0.3), source="sqlite_fts")
            for n in nodes
        ]

    def _get_popular(self, top_k: int) -> list[ExperienceHit]:
        hits = []
        for domain_id in DOMAINS:
            nodes = self._store.list_nodes(domain_id=domain_id, limit=2)
            for n in nodes:
                score = 0.3 + min(n.hit_count * 0.01, 0.2)
                hits.append(ExperienceHit(node=n, score=score, source="popular"))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    # ─── write ───

    def write(
        self,
        query: str,
        result: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write a new experience with automatic classification."""
        return self._writer.write(query, result, metadata)

    # ─── management ───

    def get_domain_stats(self, domain_id: str) -> dict[str, Any]:
        stats = self._store.get_domain_stats(domain_id)
        stats["domain_name"] = get_domain_name(domain_id)
        return stats

    def get_all_stats(self) -> dict[str, Any]:
        stats = self._store.get_all_stats()
        stats["router_stats"] = self._router.get_domain_stats()
        return stats

    def link_experience(
        self,
        source_id: str,
        target_id: str,
        relation: str = "related_to",
        weight: float = 1.0,
    ) -> None:
        self._store.add_link(source_id, target_id, relation, weight)

    def get_node(self, node_id: str) -> Optional[ExperienceNode]:
        return self._store.get_node(node_id)

    def list_nodes(
        self,
        domain_id: str = "",
        category_id: str = "",
        limit: int = 50,
    ) -> list[ExperienceNode]:
        return self._store.list_nodes(domain_id=domain_id, category_id=category_id, limit=limit)

    def delete_node(self, node_id: str) -> bool:
        return self._store.delete_node(node_id)

    def format_tree(self, domain_id: str = "") -> str:
        """Format the experience tree as a human-readable string."""
        lines = ["experience_tree/"]

        domains = [domain_id] if domain_id else list(DOMAINS.keys())
        for did in domains:
            d_name = get_domain_name(did)
            stats = self._store.get_domain_stats(did)
            node_count = stats["total_nodes"]
            lines.append(f"├── {d_name} ({did}) [{node_count} nodes]")

            for cid, c in CATEGORIES.items():
                nodes = self._store.list_nodes(domain_id=did, category_id=cid, limit=3)
                c_name = c["name"]
                if nodes:
                    lines.append(f"│   ├── {c_name} ({cid}) [{len(nodes)}+ items]")
                    for n in nodes:
                        content_preview = (n.content or "")[:60].replace("\n", " ")
                        lines.append(f"│   │   └── {n.name}: {content_preview}...")
                else:
                    lines.append(f"│   ├── {c_name} ({cid}) [empty]")

        return "\n".join(lines)


_singleton: Optional[ExperienceTree] = None


def get_experience_tree() -> ExperienceTree:
    global _singleton
    if _singleton is None:
        _singleton = ExperienceTree()
    return _singleton
