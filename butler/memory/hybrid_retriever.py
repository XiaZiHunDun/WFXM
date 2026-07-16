"""Hybrid Retriever — combines semantic search and graph-based retrieval.

This module implements a hybrid retrieval system that:
1. Uses ChromaDB for dense vector semantic search
2. Uses KnowledgeGraph for structured graph traversal
3. Fuses results from both systems for enhanced context retrieval
4. Supports multi-hop reasoning across structured and unstructured knowledge

Key components:
- HybridRetriever: Main entry point combining both retrieval methods
- RetrievalFusion: Combines and ranks results from multiple sources
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from butler.memory.knowledge_graph import KnowledgeGraph, GraphRetriever, get_knowledge_graph
from butler.memory.semantic_memory import SemanticMemory, CHROMADB_AVAILABLE, get_semantic_memory

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(
        self,
        knowledge_graph: KnowledgeGraph | None = None,
        semantic_memory: SemanticMemory | None = None,
    ):
        self._kg = knowledge_graph or get_knowledge_graph()
        self._graph_retriever = GraphRetriever(self._kg)
        self._semantic_memory = semantic_memory or get_semantic_memory()
        self._semantic_available = CHROMADB_AVAILABLE
    
    def retrieve(
        self,
        query: str,
        conversation_id: str = "default",
        max_results: int = 10,
        graph_hops: int = 2,
        semantic_top_k: int = 5,
        fusion_strategy: str = "reciprocal_rerank",
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {
            "query": query,
            "graph_results": [],
            "semantic_results": [],
            "fused_results": [],
        }
        
        graph_results = self._graph_retriever.retrieve(
            query,
            max_hops=graph_hops,
            max_results=max_results,
        )
        results["graph_results"] = graph_results
        
        if self._semantic_available:
            semantic_results = self._semantic_memory.search(
                query,
                conversation_id=conversation_id,
                top_k=semantic_top_k,
            )
            results["semantic_results"] = semantic_results
        
        fused = self._fuse_results(
            graph_results,
            semantic_results if self._semantic_available else [],
            strategy=fusion_strategy,
            top_n=max_results,
        )
        results["fused_results"] = fused
        
        return results
    
    def _fuse_results(
        self,
        graph_results: List[Dict[str, Any]],
        semantic_results: List[Dict[str, Any]],
        strategy: str = "reciprocal_rerank",
        top_n: int = 10,
    ) -> List[Dict[str, Any]]:
        all_results = []
        
        for i, result in enumerate(graph_results):
            all_results.append({
                "type": "graph",
                "source": result["entity"],
                "content": str(result),
                "rank": i + 1,
                "score": 1.0 / (i + 1),
                "raw": result,
            })
        
        for i, result in enumerate(semantic_results):
            all_results.append({
                "type": "semantic",
                "source": result.get("id", ""),
                "content": result.get("document", ""),
                "rank": i + 1,
                "score": result.get("distance", 1.0),
                "raw": result,
            })
        
        if strategy == "reciprocal_rerank":
            reciprocal_scores = {}
            for result in all_results:
                key = f"{result['type']}_{result['source']}"
                if key not in reciprocal_scores:
                    reciprocal_scores[key] = 0
                reciprocal_scores[key] += 1.0 / result["rank"]
            
            scored_results = []
            for key, score in reciprocal_scores.items():
                for result in all_results:
                    if f"{result['type']}_{result['source']}" == key:
                        result["fused_score"] = score
                        scored_results.append(result)
                        break
            
            scored_results.sort(key=lambda x: x["fused_score"], reverse=True)
            return scored_results[:top_n]
        
        elif strategy == "weighted":
            for result in all_results:
                if result["type"] == "graph":
                    result["fused_score"] = result["score"] * 0.6
                else:
                    result["fused_score"] = (1.0 - result["score"]) * 0.4
            
            all_results.sort(key=lambda x: x["fused_score"], reverse=True)
            return all_results[:top_n]
        
        else:
            return all_results[:top_n]
    
    def get_context(self, query: str, conversation_id: str = "default") -> str:
        results = self.retrieve(query, conversation_id=conversation_id)
        
        context_parts = []
        
        for result in results["fused_results"]:
            if result["type"] == "graph":
                entity_info = result["raw"]
                neighborhood = entity_info.get("neighborhood", {})
                edges = neighborhood.get("edges", [])
                if edges:
                    relations = []
                    for edge in edges[:5]:
                        relations.append(f"{edge['source']} —{edge['relation']}→ {edge['target']}")
                    context_parts.append("\n".join(relations))
            
            elif result["type"] == "semantic":
                doc = result.get("content", "")
                if doc:
                    context_parts.append(doc[:300])
        
        return "\n\n".join(context_parts)


_singleton: Optional[HybridRetriever] = None


def get_hybrid_retriever() -> HybridRetriever:
    global _singleton
    if _singleton is None:
        _singleton = HybridRetriever()
    return _singleton


__all__ = [
    "HybridRetriever",
    "get_hybrid_retriever",
]
