"""Knowledge Graph — structured knowledge representation for enhanced reasoning.

This module implements a knowledge graph system that:
- Stores entities, relations, and attributes as a graph structure
- Supports entity linking and multi-hop reasoning
- Integrates with vector search for hybrid retrieval
- Persists to SQLite for durability

Key components:
- KnowledgeGraph: Core graph storage with NetworkX
- EntityLinker: Maps text to graph entities
- GraphRetriever: Performs graph traversal and reasoning
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    def __init__(self, graph_id: str = "default", persist_dir: str | None = None):
        self._graph_id = graph_id
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        default_data_dir = os.path.join(project_root, ".wfxm_data")

        self._persist_dir = persist_dir or os.path.join(
            default_data_dir, "knowledge_graph"
        )
        os.makedirs(self._persist_dir, exist_ok=True)
        
        self._graph = nx.DiGraph()
        self._lock = threading.RLock()
        self._entity_types: Dict[str, str] = {}
        self._entity_attributes: Dict[str, Dict[str, Any]] = {}
        
        self._db_path = os.path.join(self._persist_dir, f"{graph_id}.db")
        self._ensure_db_schema()
        self._load_from_db()
    
    def _ensure_db_schema(self) -> None:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA user_version")
                version = cursor.fetchone()[0]
                
                if version == 0:
                    cursor.execute("""
                        CREATE TABLE entities (
                            id TEXT PRIMARY KEY,
                            label TEXT NOT NULL,
                            type TEXT DEFAULT '',
                            attributes_json TEXT DEFAULT '{}',
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL
                        )
                    """)
                    cursor.execute("""
                        CREATE TABLE relations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            source TEXT NOT NULL,
                            relation TEXT NOT NULL,
                            target TEXT NOT NULL,
                            attributes_json TEXT DEFAULT '{}',
                            created_at REAL NOT NULL,
                            UNIQUE(source, relation, target)
                        )
                    """)
                    cursor.execute("CREATE INDEX idx_relations_source ON relations(source)")
                    cursor.execute("CREATE INDEX idx_relations_target ON relations(target)")
                    cursor.execute("CREATE INDEX idx_relations_relation ON relations(relation)")
                    version = 1
                
                cursor.execute(f"PRAGMA user_version = {version}")
                conn.commit()
    
    def _load_from_db(self) -> None:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, label, type, attributes_json FROM entities")
                for row in cursor.fetchall():
                    entity_id, label, entity_type, attrs_json = row
                    self._graph.add_node(entity_id, label=label, type=entity_type)
                    self._entity_types[entity_id] = entity_type
                    try:
                        self._entity_attributes[entity_id] = json.loads(attrs_json) if attrs_json else {}
                    except json.JSONDecodeError:
                        self._entity_attributes[entity_id] = {}
                
                cursor.execute("SELECT source, relation, target, attributes_json FROM relations")
                for row in cursor.fetchall():
                    source, relation, target, attrs_json = row
                    try:
                        attrs = json.loads(attrs_json) if attrs_json else {}
                    except json.JSONDecodeError:
                        attrs = {}
                    self._graph.add_edge(source, target, relation=relation, **attrs)
    
    def add_entity(
        self,
        entity_id: str,
        label: str,
        entity_type: str = "",
        attributes: Dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            now = time.time()
            self._graph.add_node(entity_id, label=label, type=entity_type)
            self._entity_types[entity_id] = entity_type
            self._entity_attributes[entity_id] = attributes or {}
            
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO entities
                    (id, label, type, attributes_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (entity_id, label, entity_type, json.dumps(attributes or {}, ensure_ascii=False), now, now))
                conn.commit()
    
    def add_relation(
        self,
        source: str,
        relation: str,
        target: str,
        attributes: Dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            now = time.time()
            attrs = attributes or {}
            self._graph.add_edge(source, target, relation=relation, **attrs)
            
            with sqlite3.connect(self._db_path) as conn:
                try:
                    conn.execute("""
                        INSERT INTO relations
                        (source, relation, target, attributes_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (source, relation, target, json.dumps(attrs, ensure_ascii=False), now))
                except sqlite3.IntegrityError:
                    conn.execute("""
                        UPDATE relations
                        SET attributes_json = ?, updated_at = ?
                        WHERE source = ? AND relation = ? AND target = ?
                    """, (json.dumps(attrs, ensure_ascii=False), now, source, relation, target))
                conn.commit()
    
    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if entity_id not in self._graph:
                return None
            return {
                "id": entity_id,
                "label": self._graph.nodes[entity_id].get("label", entity_id),
                "type": self._entity_types.get(entity_id, ""),
                "attributes": self._entity_attributes.get(entity_id, {}),
            }
    
    def get_relations(self, entity_id: str, direction: str = "both") -> List[Dict[str, Any]]:
        with self._lock:
            relations = []
            if direction in ("out", "both"):
                for target in self._graph.successors(entity_id):
                    edge_data = self._graph[entity_id][target]
                    relations.append({
                        "source": entity_id,
                        "relation": edge_data.get("relation", ""),
                        "target": target,
                        "attributes": {k: v for k, v in edge_data.items() if k != "relation"},
                    })
            if direction in ("in", "both"):
                for source in self._graph.predecessors(entity_id):
                    edge_data = self._graph[source][entity_id]
                    relations.append({
                        "source": source,
                        "relation": edge_data.get("relation", ""),
                        "target": entity_id,
                        "attributes": {k: v for k, v in edge_data.items() if k != "relation"},
                    })
            return relations
    
    def search_entities(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            query_lower = query.lower()
            matches = []
            for entity_id in self._graph.nodes:
                label = self._graph.nodes[entity_id].get("label", entity_id).lower()
                if query_lower in label or query_lower in entity_id.lower():
                    matches.append({
                        "id": entity_id,
                        "label": self._graph.nodes[entity_id].get("label", entity_id),
                        "type": self._entity_types.get(entity_id, ""),
                        "score": len(query) / max(len(label), len(entity_id)),
                    })
            matches.sort(key=lambda x: x["score"], reverse=True)
            return matches[:max_results]
    
    def find_paths(
        self,
        source: str,
        target: str,
        max_hops: int = 3,
        relation_filter: List[str] | None = None,
    ) -> List[List[Dict[str, Any]]]:
        with self._lock:
            all_paths = []
            try:
                for path in nx.all_simple_paths(self._graph, source=source, target=target, cutoff=max_hops):
                    path_relations = []
                    for i in range(len(path) - 1):
                        edge_data = self._graph[path[i]][path[i + 1]]
                        relation = edge_data.get("relation", "")
                        if relation_filter and relation not in relation_filter:
                            break
                        path_relations.append({
                            "source": path[i],
                            "relation": relation,
                            "target": path[i + 1],
                        })
                    else:
                        all_paths.append(path_relations)
            except nx.NodeNotFound:
                pass
            return all_paths
    
    def get_neighborhood(self, entity_id: str, hops: int = 1) -> Dict[str, Any]:
        with self._lock:
            nodes = {entity_id}
            edges = []
            visited = set()
            queue = [(entity_id, 0)]
            
            while queue:
                node, depth = queue.pop(0)
                if node in visited or depth > hops:
                    continue
                visited.add(node)
                
                for neighbor in self._graph.successors(node):
                    if neighbor not in visited:
                        nodes.add(neighbor)
                        edge_data = self._graph[node][neighbor]
                        edges.append({
                            "source": node,
                            "relation": edge_data.get("relation", ""),
                            "target": neighbor,
                        })
                        if depth + 1 <= hops:
                            queue.append((neighbor, depth + 1))
                
                for neighbor in self._graph.predecessors(node):
                    if neighbor not in visited:
                        nodes.add(neighbor)
                        edge_data = self._graph[neighbor][node]
                        edges.append({
                            "source": neighbor,
                            "relation": edge_data.get("relation", ""),
                            "target": node,
                        })
                        if depth + 1 <= hops:
                            queue.append((neighbor, depth + 1))
            
            entities_info = {}
            for node in nodes:
                entities_info[node] = {
                    "label": self._graph.nodes[node].get("label", node),
                    "type": self._entity_types.get(node, ""),
                }
            
            return {"entities": entities_info, "edges": edges}
    
    def add_triple(self, subject: str, relation: str, obj: str) -> None:
        if subject not in self._graph:
            self.add_entity(subject, subject)
        if obj not in self._graph:
            self.add_entity(obj, obj)
        self.add_relation(subject, relation, obj)
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "entities": self._graph.number_of_nodes(),
                "relations": self._graph.number_of_edges(),
                "graph_id": self._graph_id,
                "db_path": self._db_path,
            }
    
    def clear(self) -> None:
        with self._lock:
            self._graph.clear()
            self._entity_types.clear()
            self._entity_attributes.clear()
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM entities")
                conn.execute("DELETE FROM relations")
                conn.commit()


class EntityLinker:
    def __init__(self, knowledge_graph: KnowledgeGraph):
        self._kg = knowledge_graph
    
    def link(self, text: str, top_n: int = 3) -> List[Tuple[str, float]]:
        text_lower = text.lower()
        candidates = []
        
        for entity_id in self._kg._graph.nodes:
            label = self._kg._graph.nodes[entity_id].get("label", entity_id).lower()
            entity_id_lower = entity_id.lower()
            
            if label in text_lower:
                score = len(label) / len(text_lower) + 0.5
                candidates.append((entity_id, score))
            elif entity_id_lower in text_lower:
                score = len(entity_id_lower) / len(text_lower) + 0.3
                candidates.append((entity_id, score))
            else:
                for word in text_lower.split():
                    if word in label or word in entity_id_lower:
                        score = len(word) / len(text_lower) + 0.1
                        candidates.append((entity_id, score))
                        break
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        unique = []
        seen = set()
        for entity_id, score in candidates:
            if entity_id not in seen:
                seen.add(entity_id)
                unique.append((entity_id, score))
                if len(unique) >= top_n:
                    break
        return unique


class GraphRetriever:
    def __init__(self, knowledge_graph: KnowledgeGraph):
        self._kg = knowledge_graph
    
    def retrieve(
        self,
        query: str,
        max_hops: int = 2,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        linker = EntityLinker(self._kg)
        entities = linker.link(query, top_n=5)
        
        results = []
        for entity_id, _ in entities:
            neighborhood = self._kg.get_neighborhood(entity_id, hops=max_hops)
            results.append({
                "entity": entity_id,
                "label": self._kg._graph.nodes[entity_id].get("label", entity_id),
                "neighborhood": neighborhood,
            })
        
        return results[:max_results]


_singleton: Optional[KnowledgeGraph] = None


def get_knowledge_graph(graph_id: str = "default") -> KnowledgeGraph:
    global _singleton
    if _singleton is None:
        _singleton = KnowledgeGraph(graph_id)
    return _singleton


KG_AVAILABLE = True

__all__ = [
    "KnowledgeGraph",
    "EntityLinker",
    "GraphRetriever",
    "get_knowledge_graph",
    "KG_AVAILABLE",
]
