"""Experience-based tool selector — recommends tools from historical success.

Integrates with the Experience Tree to:
1. Retrieve relevant experiences for a query
2. Extract tool recommendations from successful experiences
3. Score tools by success rate and relevance
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

try:
    from butler.memory.experience.tree import get_experience_tree
    from butler.memory.experience.store import ExperienceHit
    _EXPERIENCE_AVAILABLE = True
except ImportError:
    _EXPERIENCE_AVAILABLE = False
    get_experience_tree = lambda: None


@dataclass
class ToolRecommendation:
    """A tool recommendation with score and source."""
    tool_name: str
    score: float
    source: str  # "experience" | "taxonomy" | "semantic"
    experience_id: str | None = None
    success_rate: float = 0.0
    metadata: dict[str, Any] | None = None


class ExperienceBasedToolSelector:
    """Select tools based on historical experience from the Experience Tree."""
    
    def __init__(self):
        self._experience_tree = get_experience_tree() if _EXPERIENCE_AVAILABLE else None
        self._tool_taxonomy = self._load_tool_taxonomy()
    
    def _load_tool_taxonomy(self) -> dict[str, list[str]]:
        """Load default tool taxonomy for fallback."""
        return {
            "agent_dev": ["delegate_task", "skill_view", "skills_list", "run_workflow"],
            "database": ["execute_code", "terminal", "read_file"],
            "llm_usage": ["call_llm", "embed_text", "web_search"],
            "code_engineering": ["read_file", "write_file", "patch", "search_files", "execute_code"],
            "dev_ops": ["terminal", "run_workflow", "delegate_task"],
            "network_info": ["web_search", "web_fetch"],
            "daily_life": ["reminder", "memo", "habits"],
            "project_mgmt": ["project_todos", "session_todos"],
        }
    
    def select_tools(self, query: str, top_k: int = 5) -> list[ToolRecommendation]:
        """Select tools based on experience retrieval.
        
        Args:
            query: The user query or task description
            top_k: Maximum number of tools to return
            
        Returns:
            List of ToolRecommendation sorted by score
        """
        recommendations: dict[str, ToolRecommendation] = {}
        
        # 1. Try experience-based selection
        if self._experience_tree:
            exp_recommendations = self._select_from_experience(query, top_k)
            for rec in exp_recommendations:
                recommendations[rec.tool_name] = rec
        
        # 2. Fallback to taxonomy-based selection
        if len(recommendations) < top_k:
            taxonomy_recommendations = self._select_from_taxonomy(query, top_k - len(recommendations))
            for rec in taxonomy_recommendations:
                if rec.tool_name not in recommendations:
                    recommendations[rec.tool_name] = rec
        
        # 3. Sort and return
        sorted_recs = sorted(recommendations.values(), key=lambda r: r.score, reverse=True)
        return sorted_recs[:top_k]
    
    def _select_from_experience(self, query: str, top_k: int) -> list[ToolRecommendation]:
        """Select tools from experience hits."""
        if not self._experience_tree:
            return []
        
        try:
            hits = self._experience_tree.retrieve(query, top_k=top_k * 3)
            recommendations: dict[str, ToolRecommendation] = {}
            
            for hit in hits:
                tool_name = self._extract_tool_name(hit)
                if not tool_name:
                    continue
                
                # Calculate score based on experience success
                base_score = hit.score
                success_rate = getattr(hit.node, 'success_rate', 0.0)
                
                # Boost score by success rate
                adjusted_score = base_score * (1.0 + success_rate * 0.5)
                
                # Update or create recommendation
                if tool_name in recommendations:
                    # Merge: boost score if already recommended
                    existing = recommendations[tool_name]
                    existing.score = max(existing.score, adjusted_score)
                else:
                    recommendations[tool_name] = ToolRecommendation(
                        tool_name=tool_name,
                        score=adjusted_score,
                        source="experience",
                        experience_id=hit.node.node_id,
                        success_rate=success_rate,
                        metadata={
                            "domain": hit.node.domain,
                            "category": hit.node.category,
                        },
                    )
            
            return sorted(recommendations.values(), key=lambda r: r.score, reverse=True)[:top_k]
        
        except Exception as e:
            logger.debug("Experience-based tool selection failed: %s", e)
            return []
    
    def _extract_tool_name(self, hit) -> str | None:
        """Extract tool name from an experience hit."""
        # Check metadata for explicit tool_name
        if hasattr(hit.node, 'metadata') and hit.node.metadata:
            tool_name = hit.node.metadata.get("tool_name")
            if tool_name:
                return tool_name
        
        # Check category
        if hit.node.category == "tools":
            # Extract from name
            name = hit.node.name
            # Common patterns: "tool_name: description" or just "tool_name"
            if ":" in name:
                return name.split(":")[0].strip()
            return name.lower().replace(" ", "_")
        
        # Check content for tool mentions
        content = hit.node.content or ""
        import re
        tool_patterns = [
            r"tool[:\s]+`?([a-z_]+)`?",
            r"调用[:\s]+`?([a-z_]+)`?",
            r"used[:\s]+`?([a-z_]+)`?",
        ]
        for pattern in tool_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).lower()
        
        return None
    
    def _select_from_taxonomy(self, query: str, top_k: int) -> list[ToolRecommendation]:
        """Select tools from taxonomy based on query domain."""
        q = query.lower()
        
        # Simple keyword-based domain matching
        domain_scores: dict[str, float] = {}
        for domain, tools in self._tool_taxonomy.items():
            if domain in q:
                domain_scores[domain] = 0.3
        
        # Check for specific tool mentions
        all_tools = set()
        for tools in self._tool_taxonomy.values():
            all_tools.update(tools)
        
        matched_tools: list[ToolRecommendation] = []
        for tool in all_tools:
            if tool.replace("_", " ") in q or tool in q:
                matched_tools.append(ToolRecommendation(
                    tool_name=tool,
                    score=0.2,
                    source="taxonomy",
                ))
        
        # Add domain-based tools
        for domain, score in sorted(domain_scores.items(), key=lambda x: x[1], reverse=True):
            for tool in self._tool_taxonomy.get(domain, []):
                if not any(r.tool_name == tool for r in matched_tools):
                    matched_tools.append(ToolRecommendation(
                        tool_name=tool,
                        score=score,
                        source="taxonomy",
                    ))
        
        return sorted(matched_tools, key=lambda r: r.score, reverse=True)[:top_k]
    
    def get_tools_for_domain(self, domain_id: str) -> list[str]:
        """Get recommended tools for a specific domain."""
        return self._tool_taxonomy.get(domain_id, [])
    
    def record_tool_usage(self, tool_name: str, query: str, success: bool) -> None:
        """Record a tool usage to the experience tree for future learning."""
        if not self._experience_tree:
            return
        
        try:
            from butler.memory.experience.tree import ExperienceTree
            tree = self._experience_tree
            
            # Determine domain from query
            from butler.memory.experience.domain_router import DomainRouter
            router = DomainRouter()
            domain_id, _ = router.route(query)
            
            # Write experience
            tree.write(
                query=query,
                result=f"Tool {tool_name} {'succeeded' if success else 'failed'}",
                metadata={
                    "tool_name": tool_name,
                    "success": success,
                    "type": "tool_usage",
                },
            )
            
            logger.debug("Recorded tool usage: %s (success=%s)", tool_name, success)
        
        except Exception as e:
            logger.debug("Failed to record tool usage: %s", e)


# Singleton
_selector: ExperienceBasedToolSelector | None = None


def get_tool_selector() -> ExperienceBasedToolSelector:
    """Get the singleton tool selector instance."""
    global _selector
    if _selector is None:
        _selector = ExperienceBasedToolSelector()
    return _selector


def select_tools(query: str, top_k: int = 5) -> list[ToolRecommendation]:
    """Convenience function to select tools."""
    return get_tool_selector().select_tools(query, top_k)