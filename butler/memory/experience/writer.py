"""ExperienceWriter — writes new experiences with automatic classification.

After a tool/skill executes and produces a result, the writer:
1. Classifies the (query, result) pair into domain + category
2. Extracts structured knowledge (triplets, key technologies)
3. Stores the experience node in SQLite + ChromaDB + KnowledgeGraph
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from butler.memory.experience.classifier import DomainClassifier
from butler.memory.experience.store import ExperienceNode, ExperienceStore

logger = logging.getLogger(__name__)

try:
    from butler.memory.triplets import extract_triplets_from_text
except ImportError:
    extract_triplets_from_text = lambda x, **kw: []

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


class ExperienceWriter:
    def __init__(self, store: ExperienceStore | None = None):
        self._store = store or ExperienceStore()
        self._classifier = DomainClassifier()
        self._semantic = get_semantic_memory() if CHROMADB_AVAILABLE else None
        self._kg = get_knowledge_graph() if KG_AVAILABLE else None

    def write(
        self,
        query: str,
        result: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Write a new experience. Returns the node_id."""
        meta = metadata or {}

        # Step 1: Classify
        domain_id, category_id, confidence = self._classifier.classify(
            query, result, meta
        )

        # Step 2: Generate node
        content = self._build_content(query, result, meta)
        name = self._generate_name(query, meta)
        node_id = self._generate_id(domain_id, category_id, name, content)

        node = ExperienceNode(
            node_id=node_id,
            domain=domain_id,
            category=category_id,
            name=name,
            content=content,
            metadata={
                "query": query[:200],
                "confidence": confidence,
                **meta,
            },
        )

        # Step 3: Store in SQLite
        self._store.save_node(node)

        # Step 4: Store in ChromaDB (semantic)
        if self._semantic and CHROMADB_AVAILABLE:
            try:
                self._semantic.add_turn_summary(
                    turn_number=int(time.time()),
                    user_intent=query[:200],
                    assistant_action=result[:200],
                    result_summary=content[:500],
                    conversation_id=domain_id,
                )
                node.embedding_id = f"exp_{domain_id}_{node_id}"
            except Exception as e:
                logger.debug("ChromaDB write failed: %s", e)

        # Step 5: Extract and store triplets in KnowledgeGraph
        if self._kg and KG_AVAILABLE:
            try:
                triplets = extract_triplets_from_text(content, max_triplets=5)
                for triplet in triplets:
                    self._kg.add_triple(
                        triplet["subject"],
                        triplet["relation"],
                        triplet["object"],
                    )
                if triplets:
                    node.kg_entity_id = triplets[0]["subject"]
            except Exception as e:
                logger.debug("KnowledgeGraph write failed: %s", e)

        logger.info(
            "Experience written: domain=%s category=%s confidence=%.2f node=%s",
            domain_id, category_id, confidence, node_id,
        )
        return node_id

    def _build_content(self, query: str, result: str, meta: dict) -> str:
        parts = [f"Q: {query[:300]}"]
        if result:
            parts.append(f"R: {result[:500]}")
        if meta:
            for key in ("tool_name", "skill_name", "workflow_id"):
                if meta.get(key):
                    parts.append(f"{key}: {meta[key]}")
        return "\n".join(parts)

    def _generate_name(self, query: str, meta: dict) -> str:
        if meta.get("tool_name"):
            return meta["tool_name"]
        if meta.get("skill_name"):
            return meta["skill_name"]
        if meta.get("workflow_id"):
            return meta["workflow_id"]
        # Use first meaningful words of query
        words = query.strip().split()[:5]
        return "_".join(words) if words else "experience"

    def _generate_id(self, domain: str, category: str, name: str, content: str) -> str:
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        safe_name = name.replace(" ", "_").replace("/", "_")[:50]
        return f"{domain}/{category}/{safe_name}_{content_hash}"
