"""ExperienceRetriever — retrieves experiences from multiple backends.

Combines:
- SQLite FTS5 full-text search (structured, fast)
- ChromaDB semantic search (fuzzy, meaning-based)
- KnowledgeGraph traversal (relational, multi-hop)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from butler.memory.experience.store import ExperienceNode, ExperienceHit, ExperienceStore

logger = logging.getLogger(__name__)

try:
    from butler.memory.semantic_memory import get_semantic_memory, CHROMADB_AVAILABLE
except ImportError:
    CHROMADB_AVAILABLE = False
    get_semantic_memory = lambda: None

try:
    from butler.memory.knowledge_graph import get_knowledge_graph, KG_AVAILABLE
except ImportError:
    KG_AVAILABLE = False
    get_knowledge_graph = lambda: None


class ExperienceRetriever:
    def __init__(self, store: ExperienceStore | None = None):
        self._store = store or ExperienceStore()
        self._semantic = get_semantic_memory() if CHROMADB_AVAILABLE else None
        self._kg = get_knowledge_graph() if KG_AVAILABLE else None

    def retrieve(
        self,
        domain_id: str,
        query: str,
        category_id: str = "",
        top_k: int = 5,
    ) -> list[ExperienceHit]:
        """Retrieve experiences for a domain+query, optionally filtered by category."""
        hits: list[ExperienceHit] = []

        # Source 1: SQLite FTS5
        fts_hits = self._retrieve_from_sqlite(domain_id, query, category_id, top_k)
        hits.extend(fts_hits)

        # Source 2: ChromaDB semantic search
        semantic_hits = self._retrieve_from_chromadb(query, domain_id, top_k)
        hits.extend(semantic_hits)

        # Source 3: KnowledgeGraph traversal
        kg_hits = self._retrieve_from_knowledge_graph(query, top_k)
        hits.extend(kg_hits)

        # Deduplicate and rank
        return self._rank_and_deduplicate(hits, top_k)

    def _retrieve_from_sqlite(
        self,
        domain_id: str,
        query: str,
        category_id: str,
        limit: int,
    ) -> list[ExperienceHit]:
        try:
            nodes = self._store.search_by_domain(
                domain_id, query=query, category_id=category_id, limit=limit
            )
            hits = []
            for node in nodes:
                score = 0.5 + min(node.hit_count * 0.01, 0.3)
                hits.append(ExperienceHit(node=node, score=score, source="sqlite"))
            return hits
        except Exception as e:
            logger.debug("SQLite retrieval failed: %s", e)
            return []

    def _retrieve_from_chromadb(
        self,
        query: str,
        domain_id: str,
        limit: int,
    ) -> list[ExperienceHit]:
        if not self._semantic or not CHROMADB_AVAILABLE:
            return []

        try:
            results = self._semantic.search(
                query, conversation_id=domain_id, top_k=limit
            )
            hits = []
            for r in results:
                score = max(1.0 - r.get("distance", 1.0), 0.0)
                node = ExperienceNode(
                    node_id=r.get("id", ""),
                    domain=domain_id,
                    category="recent_conversations",
                    name=r.get("metadata", {}).get("type", "semantic"),
                    content=r.get("document", ""),
                    embedding_id=r.get("id", ""),
                )
                hits.append(ExperienceHit(node=node, score=score, source="chromadb"))
            return hits
        except Exception as e:
            logger.debug("ChromaDB retrieval failed: %s", e)
            return []

    def _retrieve_from_knowledge_graph(
        self,
        query: str,
        limit: int,
    ) -> list[ExperienceHit]:
        if not self._kg or not KG_AVAILABLE:
            return []

        try:
            from butler.memory.knowledge_graph import EntityLinker, GraphRetriever
            retriever = GraphRetriever(self._kg)
            results = retriever.retrieve(query, max_hops=2, max_results=limit)
            hits = []
            for r in results:
                entity_id = r.get("entity", "")
                neighborhood = r.get("neighborhood", {})
                edges = neighborhood.get("edges", [])
                content_parts = []
                for edge in edges[:5]:
                    content_parts.append(
                        f"{edge['source']} —{edge['relation']}→ {edge['target']}"
                    )
                node = ExperienceNode(
                    node_id=f"kg/{entity_id}",
                    domain="",
                    category="knowledge_facts",
                    name=entity_id,
                    content="\n".join(content_parts),
                    kg_entity_id=entity_id,
                )
                score = 0.6 + min(len(edges) * 0.02, 0.2)
                hits.append(ExperienceHit(node=node, score=score, source="knowledge_graph"))
            return hits
        except Exception as e:
            logger.debug("KnowledgeGraph retrieval failed: %s", e)
            return []

    def _rank_and_deduplicate(
        self,
        hits: list[ExperienceHit],
        top_k: int,
    ) -> list[ExperienceHit]:
        seen: set[str] = set()
        unique: list[ExperienceHit] = []
        for hit in hits:
            key = hit.node.node_id
            if key in seen:
                # Merge: boost score for duplicate hits from different sources
                for existing in unique:
                    if existing.node.node_id == key:
                        existing.score = max(existing.score, hit.score) + 0.1
                        break
                continue
            seen.add(key)
            unique.append(hit)

        unique.sort(key=lambda h: h.score, reverse=True)
        return unique[:top_k]
