"""Tool discovery service — semantic-based tool recommendation.

Uses embeddings to match user queries with tool descriptions,
enabling discovery even when users don't know the exact tool name.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

try:
    from butler.memory.embedding import get_embedder, cosine_similarity
    _EMBEDDER_AVAILABLE = True
except ImportError:
    _EMBEDDER_AVAILABLE = False
    get_embedder = lambda: None
    cosine_similarity = lambda a, b: 0.0


class ToolDiscovery:
    """Semantic tool discovery using embeddings."""
    
    def __init__(self):
        self._embedder = get_embedder() if _EMBEDDER_AVAILABLE else None
        self._tool_embeddings: dict[str, list[float]] = {}
        self._tool_descriptions: dict[str, str] = {}
        self._lock = threading.Lock()
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize by computing embeddings for all registered tools."""
        if self._initialized:
            return
        
        if not self._embedder:
            logger.debug("Embedder not available, semantic discovery disabled")
            return
        
        from butler.tools.registry import _REGISTRY, _ensure_builtins
        _ensure_builtins()
        
        with self._lock:
            if self._initialized:
                return
            
            for name, entry in _REGISTRY.items():
                # Combine name and description for better matching
                text = f"{name}: {entry.description}"
                try:
                    embedding = self._embedder.embed(text)
                    self._tool_embeddings[name] = embedding
                    self._tool_descriptions[name] = entry.description
                except Exception as e:
                    logger.debug("Failed to embed tool %s: %s", name, e)
            
            self._initialized = True
            logger.info("Initialized semantic discovery for %d tools", len(self._tool_embeddings))
    
    def discover(self, query: str, top_k: int = 5, threshold: float = 0.3) -> list[dict[str, Any]]:
        """Discover tools based on semantic similarity to query.
        
        Args:
            query: User query or task description
            top_k: Maximum number of tools to return
            threshold: Minimum similarity threshold (0-1)
            
        Returns:
            List of dicts with tool_name, similarity, description
        """
        if not self._embedder:
            return []
        
        self.initialize()
        
        if not self._tool_embeddings:
            return []
        
        try:
            query_embedding = self._embedder.embed(query)
            
            # Compute similarity with all tools
            scores: list[tuple[str, float]] = []
            for name, tool_embedding in self._tool_embeddings.items():
                sim = cosine_similarity(query_embedding, tool_embedding)
                if sim >= threshold:
                    scores.append((name, sim))
            
            # Sort by similarity
            scores.sort(key=lambda x: x[1], reverse=True)
            
            # Format results
            results = []
            for name, sim in scores[:top_k]:
                results.append({
                    "tool_name": name,
                    "similarity": round(sim, 4),
                    "description": self._tool_descriptions.get(name, ""),
                })
            
            return results
        
        except Exception as e:
            logger.debug("Semantic discovery failed: %s", e)
            return []
    
    def discover_with_domain(self, query: str, domain_id: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Discover tools combining semantic similarity with domain filtering.
        
        Args:
            query: User query
            domain_id: Domain to prioritize
            top_k: Maximum results
            
        Returns:
            List of tool recommendations
        """
        from butler.tools.tool_taxonomy import get_tools_by_domain
        
        # Get domain tools for prioritization
        domain_tools = set(get_tools_by_domain(domain_id))
        
        # Discover semantically
        semantic_results = self.discover(query, top_k=top_k * 2)
        
        # Boost scores for domain tools
        boosted = []
        for result in semantic_results:
            tool_name = result["tool_name"]
            score = result["similarity"]
            
            if tool_name in domain_tools:
                # Boost domain tools
                score = min(score * 1.5, 1.0)
                result["similarity"] = round(score, 4)
                result["domain_match"] = True
            else:
                result["domain_match"] = False
            
            boosted.append(result)
        
        # Also add any domain tools not found semantically
        semantic_tools = {r["tool_name"] for r in semantic_results}
        for tool_name in domain_tools:
            if tool_name not in semantic_tools:
                boosted.append({
                    "tool_name": tool_name,
                    "similarity": 0.3,
                    "description": self._tool_descriptions.get(tool_name, ""),
                    "domain_match": True,
                })
        
        # Sort and return
        boosted.sort(key=lambda x: x["similarity"], reverse=True)
        return boosted[:top_k]
    
    def get_similar_tools(self, tool_name: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Find tools similar to a given tool.
        
        Args:
            tool_name: The reference tool
            top_k: Maximum results
            
        Returns:
            List of similar tools with similarity scores
        """
        if tool_name not in self._tool_embeddings:
            return []
        
        ref_embedding = self._tool_embeddings[tool_name]
        
        scores: list[tuple[str, float]] = []
        for name, embedding in self._tool_embeddings.items():
            if name == tool_name:
                continue
            sim = cosine_similarity(ref_embedding, embedding)
            scores.append((name, sim))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return [
            {
                "tool_name": name,
                "similarity": round(sim, 4),
                "description": self._tool_descriptions.get(name, ""),
            }
            for name, sim in scores[:top_k]
        ]
    
    def refresh(self) -> None:
        """Re-compute embeddings (call when tools change)."""
        with self._lock:
            self._initialized = False
            self._tool_embeddings.clear()
            self._tool_descriptions.clear()
        self.initialize()


# Singleton
_discovery: ToolDiscovery | None = None


def get_tool_discovery() -> ToolDiscovery:
    """Get the singleton tool discovery instance."""
    global _discovery
    if _discovery is None:
        _discovery = ToolDiscovery()
    return _discovery


def discover_tools(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Convenience function to discover tools."""
    return get_tool_discovery().discover(query, top_k)