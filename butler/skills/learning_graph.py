"""Learning graph — visualize skill / memory relationships for the agent.

Provides a lightweight in-memory graph with three node types
(skill, memory, and skill-as-memory) and three edge types
(related, lexical, usage).  Uses only the Python standard library.
"""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SkillNode:
    """A skill node in the learning graph."""

    name: str
    category: str
    source: str = "builtin"
    use_count: int = 0
    state: str = "active"
    related: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    created_by: str | None = None
    pinned: bool = False


@dataclass
class MemoryNode:
    """A memory node in the learning graph."""

    name: str
    source: str = "MEMORY.md"
    category: str = "memory"
    content_preview: str = ""
    related_skills: list[str] = field(default_factory=list)
    timestamp: float = 0.0


@dataclass
class GraphEdge:
    """A typed edge between two nodes."""

    from_node: str
    to_node: str
    edge_type: str = "related"
    weight: float = 1.0


# ---------------------------------------------------------------------------
# Helpers – Jaccard similarity
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Lower-case word-level token set for a piece of text."""
    return {w for w in text.lower().split() if w}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard index between two token sets."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _make_memory_name(content: str, title: str = "") -> str:
    """Derive a deterministic node name from title or content hash."""
    t = (title or "").strip()
    if t:
        return t
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    return f"mem_{digest}"


# ---------------------------------------------------------------------------
# LearningGraph
# ---------------------------------------------------------------------------

class LearningGraph:
    """In-memory learning graph for skills and memories.

    Nodes are stored in three dicts keyed by *name* (the unique node id).
    Edges are kept in an adjacency map for fast traversal and a separate
    list for serialisation.
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillNode] = {}
        self._memories: dict[str, MemoryNode] = {}
        self._edges: dict[str, GraphEdge] = {}  # keyed by "from->to|type"
        self._adj: dict[str, dict[str, list[str]]] = {}  # node -> neighbour -> [edge_types]

    # -- node insertion ------------------------------------------------------

    def add_skill_node(self, metadata: dict[str, Any] | SkillNode) -> SkillNode:
        """Add (or replace) a skill node from a metadata dict or SkillNode.

        Expected keys (all optional besides *name*):
        ``name``, ``category``, ``source``, ``use_count``, ``state``,
        ``related``, ``timestamp``, ``created_by``, ``pinned``.
        """
        if isinstance(metadata, SkillNode):
            node = metadata
            self._skills[node.name] = node
            self._adj.setdefault(node.name, {})
            return node

        name = str(metadata.get("name", "")).strip()
        if not name:
            raise ValueError("Skill node requires a 'name' field")

        node = SkillNode(
            name=name,
            category=str(metadata.get("category", "general") or "general"),
            source=str(metadata.get("source", "builtin") or "builtin"),
            use_count=int(metadata.get("use_count", 0) or 0),
            state=str(metadata.get("state", "active") or "active"),
            related=list(metadata.get("related") or []),
            timestamp=float(metadata.get("timestamp", 0.0) or 0.0),
            created_by=metadata.get("created_by"),
            pinned=bool(metadata.get("pinned", False)),
        )
        self._skills[name] = node
        self._adj.setdefault(name, {})
        return node

    def add_memory_node(self, memory_entry: dict[str, Any]) -> MemoryNode:
        """Add (or replace) a memory node from a memory-entry dict.

        Expected keys: ``name`` (or *content* + *title*), ``source``,
        ``category``, ``content_preview``, ``related_skills``, ``timestamp``.
        """
        name = str(memory_entry.get("name", "") or "").strip()
        if not name:
            name = _make_memory_name(
                str(memory_entry.get("content", "") or ""),
                str(memory_entry.get("title", "") or ""),
            )
        if not name:
            raise ValueError("Memory node requires a 'name' or derivable content")

        node = MemoryNode(
            name=name,
            source=str(memory_entry.get("source", "MEMORY.md") or "MEMORY.md"),
            category=str(memory_entry.get("category", "memory") or "memory"),
            content_preview=str(memory_entry.get("content_preview", "") or "")[:200],
            related_skills=list(memory_entry.get("related_skills") or []),
            timestamp=float(memory_entry.get("timestamp", 0.0) or 0.0),
        )
        self._memories[name] = node
        self._adj.setdefault(name, {})
        return node

    # -- edge insertion ------------------------------------------------------

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str = "related",
        weight: float = 1.0,
    ) -> GraphEdge:
        """Connect two nodes with a typed edge."""
        if from_id not in self._adj:
            self._adj[from_id] = {}
        if to_id not in self._adj:
            self._adj[to_id] = {}

        edge = GraphEdge(
            from_node=from_id,
            to_node=to_id,
            edge_type=edge_type,
            weight=weight,
        )
        key = f"{from_id}->{to_id}|{edge_type}"
        self._edges[key] = edge
        self._adj[from_id].setdefault(to_id, []).append(edge_type)
        return edge

    # -- query helpers -------------------------------------------------------

    def _all_node_names(self) -> set[str]:
        return set(self._skills) | set(self._memories)

    def get_related_skills(self, skill_name: str) -> list[str]:
        """Return direct skill-neighbours of *skill_name* (any edge type)."""
        if skill_name not in self._adj:
            return []
        result: set[str] = set()
        for neighbour in self._adj[skill_name]:
            if neighbour in self._skills:
                result.add(neighbour)
        return sorted(result)

    def get_related_memories(self, memory_name: str) -> list[str]:
        """Return skill neighbours connected to *memory_name*."""
        if memory_name not in self._adj:
            return []
        result: set[str] = set()
        for neighbour in self._adj[memory_name]:
            if neighbour in self._skills:
                result.add(neighbour)
        return sorted(result)

    def shortest_path(self, from_id: str, to_id: str) -> list[str] | None:
        """BFS shortest path between two nodes, or *None* if unreachable."""
        if from_id not in self._adj or to_id not in self._adj:
            return None
        if from_id == to_id:
            return [from_id]

        visited: set[str] = {from_id}
        queue: deque[str] = deque([from_id])
        parent: dict[str, str] = {}

        while queue:
            current = queue.popleft()
            for neighbour in self._adj.get(current, {}):
                if neighbour in visited:
                    continue
                visited.add(neighbour)
                parent[neighbour] = current
                if neighbour == to_id:
                    path = [to_id]
                    while path[-1] != from_id:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                queue.append(neighbour)
        return None

    def neighbors(self, node_id: str, depth: int = 1) -> list[str]:
        """Return all nodes within *depth* hops of *node_id* (exclusive)."""
        if node_id not in self._adj or depth < 1:
            return []
        visited: set[str] = {node_id}
        frontier: set[str] = {node_id}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for n in frontier:
                for nb in self._adj.get(n, {}):
                    if nb not in visited:
                        visited.add(nb)
                        next_frontier.add(nb)
            if not next_frontier:
                break
            frontier = next_frontier
        visited.discard(node_id)
        return sorted(visited)

    # -- serialisation / stats -----------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of the graph."""
        skill_list = [
            {
                "name": s.name,
                "category": s.category,
                "source": s.source,
                "use_count": s.use_count,
                "state": s.state,
                "related": list(s.related),
                "timestamp": s.timestamp,
                "created_by": s.created_by,
                "pinned": s.pinned,
            }
            for s in self._skills.values()
        ]
        memory_list = [
            {
                "name": m.name,
                "source": m.source,
                "category": m.category,
                "content_preview": m.content_preview,
                "related_skills": list(m.related_skills),
                "timestamp": m.timestamp,
            }
            for m in self._memories.values()
        ]
        edge_list = [
            {
                "from_node": e.from_node,
                "to_node": e.to_node,
                "edge_type": e.edge_type,
                "weight": e.weight,
            }
            for e in self._edges.values()
        ]
        return {"skills": skill_list, "memories": memory_list, "edges": edge_list}

    def stats(self) -> dict[str, Any]:
        """Return summary statistics: node/edge counts by type + density."""
        skill_count = len(self._skills)
        memory_count = len(self._memories)
        total_nodes = skill_count + memory_count

        edge_type_counts: dict[str, int] = {}
        for e in self._edges.values():
            edge_type_counts[e.edge_type] = edge_type_counts.get(e.edge_type, 0) + 1

        total_edges = len(self._edges)
        density = 0.0
        if total_nodes >= 2:
            max_possible = total_nodes * (total_nodes - 1)
            density = total_edges / max_possible if max_possible > 0 else 0.0

        return {
            "skill_count": skill_count,
            "memory_count": memory_count,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "edge_type_counts": edge_type_counts,
            "density": round(density, 6),
        }

    def filter_by_category(self, category: str) -> LearningGraph:
        """Return a new ``LearningGraph`` restricted to *category* nodes."""
        g = LearningGraph()
        for s in self._skills.values():
            if s.category == category:
                g._skills[s.name] = s
                g._adj.setdefault(s.name, {})
        for m in self._memories.values():
            if m.category == category:
                g._memories[m.name] = m
                g._adj.setdefault(m.name, {})
        for key, edge in self._edges.items():
            if edge.from_node in g._adj and edge.to_node in g._adj:
                g._edges[key] = edge
                g._adj[edge.from_node].setdefault(edge.to_node, []).append(edge.edge_type)
        return g

    # -- high-level builder --------------------------------------------------

    def build(
        self,
        skill_registry: Iterable[dict[str, Any]] | Any,
        memory_provider: Any = None,
    ) -> None:
        """Populate the graph from a skill registry and optional memory.

        *skill_registry* is an iterable of skill metadata dicts (each
        having at least a ``name`` key).  *memory_provider* is an
        optional object with a ``list_memories()`` method returning
        memory-entry dicts, **or** a plain iterable of memory entries.
        """
        skills_list: list[dict[str, Any]]
        if hasattr(skill_registry, "list_skills"):
            skills_list = list(skill_registry.list_skills())
        elif hasattr(skill_registry, "__iter__"):
            skills_list = list(skill_registry)
        else:
            raise TypeError(
                "skill_registry must be iterable or have a list_skills() method"
            )

        # 1. Skill nodes
        for sk in skills_list:
            self.add_skill_node(sk)

        # 2. Memory nodes
        memories_list: list[dict[str, Any]] = []
        if memory_provider is not None:
            if hasattr(memory_provider, "list_memories"):
                memories_list = list(memory_provider.list_memories())
            elif hasattr(memory_provider, "__iter__"):
                memories_list = list(memory_provider)
        for mem in memories_list:
            self.add_memory_node(mem)

        # 3. Skill ↔ skill edges (declared related)
        for edge in GraphBuilder.build_skill_edges(skills_list):
            self.add_edge(edge.from_node, edge.to_node, edge.edge_type, edge.weight)

        # 4. Memory ↔ skill lexical edges
        if memories_list:
            mem_edges = GraphBuilder.build_memory_skill_edges(memories_list, skills_list)
            for edge in mem_edges:
                self.add_edge(edge.from_node, edge.to_node, edge.edge_type, edge.weight)


# ---------------------------------------------------------------------------
# GraphBuilder helpers
# ---------------------------------------------------------------------------

class GraphBuilder:
    """Static helper methods for constructing graph edges."""

    @staticmethod
    def build_skill_edges(
        skills: Iterable[dict[str, Any]],
    ) -> list[GraphEdge]:
        """Create ``related`` edges from each skill's declared ``related`` list."""
        edges: list[GraphEdge] = []
        seen: set[tuple[str, str]] = set()
        for sk in skills:
            name = str(sk.get("name", "") or "")
            if not name:
                continue
            for related in sk.get("related") or []:
                target = str(related).strip()
                if not target or target == name:
                    continue
                pair = (name, target)
                if pair in seen:
                    continue
                seen.add(pair)
                edges.append(
                    GraphEdge(
                        from_node=name,
                        to_node=target,
                        edge_type="related",
                        weight=1.0,
                    )
                )
        return edges

    @staticmethod
    def build_memory_skill_edges(
        memories: Iterable[dict[str, Any]],
        skills: Iterable[dict[str, Any]],
        threshold: float = 0.15,
    ) -> list[GraphEdge]:
        """Create ``lexical`` edges where a memory text overlaps a skill text.

        Uses word-level Jaccard similarity.  Edges below *threshold* are
        skipped.
        """
        skill_docs: list[tuple[str, set[str]]] = []
        for sk in skills:
            name = str(sk.get("name", "") or "")
            if not name:
                continue
            text = " ".join(
                [
                    str(sk.get("description", "") or ""),
                    str(sk.get("content", "") or ""),
                    str(sk.get("name", "") or ""),
                ]
            )
            tokens = _tokenize(text)
            # also add the name as a strong token so exact name matches
            # always produce a reasonable overlap
            tokens.update(_tokenize(name))
            skill_docs.append((name, tokens))

        edges: list[GraphEdge] = []
        for mem in memories:
            mem_name = str(mem.get("name", "") or "")
            mem_text = str(
                mem.get("content", "") or mem.get("content_preview", "") or ""
            )
            if not mem_name:
                continue
            mem_tokens = _tokenize(mem_text) | _tokenize(mem_name)
            for sk_name, sk_tokens in skill_docs:
                sim = _jaccard(mem_tokens, sk_tokens)
                if sim >= threshold:
                    edges.append(
                        GraphEdge(
                            from_node=mem_name,
                            to_node=sk_name,
                            edge_type="lexical",
                            weight=round(sim, 4),
                        )
                    )
        return edges

    @staticmethod
    def compute_edge_density(graph: LearningGraph) -> float:
        """Measure graph connectivity in [0, 1]."""
        stats = graph.stats()
        return float(stats["density"])


# ---------------------------------------------------------------------------
# Convenience alias
# ---------------------------------------------------------------------------

__all__ = [
    "SkillNode",
    "MemoryNode",
    "GraphEdge",
    "LearningGraph",
    "GraphBuilder",
]
