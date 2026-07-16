"""Knowledge Graph Tests — validate graph storage, entity linking, and retrieval."""

import pytest

from butler.memory.knowledge_graph import KnowledgeGraph, EntityLinker, GraphRetriever
from butler.memory.hybrid_retriever import HybridRetriever


class TestKnowledgeGraphBasics:
    def setup_method(self):
        self.kg = KnowledgeGraph("test_graph")
        self.kg.clear()
    
    def test_add_entity(self):
        self.kg.add_entity("FastAPI", "FastAPI", "framework", {"version": "0.100.0"})
        entity = self.kg.get_entity("FastAPI")
        assert entity is not None
        assert entity["label"] == "FastAPI"
        assert entity["type"] == "framework"
        assert entity["attributes"]["version"] == "0.100.0"
    
    def test_add_relation(self):
        self.kg.add_entity("auth_module", "用户认证模块", "module")
        self.kg.add_entity("FastAPI", "FastAPI", "framework")
        self.kg.add_relation("auth_module", "使用", "FastAPI")
        
        relations = self.kg.get_relations("auth_module")
        assert len(relations) == 1
        assert relations[0]["relation"] == "使用"
        assert relations[0]["target"] == "FastAPI"
    
    def test_add_triple(self):
        self.kg.add_triple("项目", "采用", "FastAPI")
        relations = self.kg.get_relations("项目")
        assert len(relations) == 1
        assert relations[0]["relation"] == "采用"
        assert relations[0]["target"] == "FastAPI"
    
    def test_search_entities(self):
        self.kg.add_entity("FastAPI", "FastAPI框架", "framework")
        self.kg.add_entity("PostgreSQL", "PostgreSQL数据库", "database")
        
        results = self.kg.search_entities("框架")
        assert len(results) >= 1
        assert any(r["id"] == "FastAPI" for r in results)
    
    def test_find_paths(self):
        self.kg.add_triple("项目", "使用", "认证模块")
        self.kg.add_triple("认证模块", "依赖", "FastAPI")
        self.kg.add_triple("FastAPI", "依赖", "Python")
        
        paths = self.kg.find_paths("项目", "Python", max_hops=3)
        assert len(paths) >= 1
        
        path_relations = [r["relation"] for r in paths[0]]
        assert "使用" in path_relations
        assert "依赖" in path_relations
    
    def test_get_neighborhood(self):
        self.kg.add_triple("认证模块", "使用", "FastAPI")
        self.kg.add_triple("认证模块", "使用", "Redis")
        self.kg.add_triple("FastAPI", "依赖", "Python")
        
        neighborhood = self.kg.get_neighborhood("认证模块", hops=2)
        assert "认证模块" in neighborhood["entities"]
        assert "FastAPI" in neighborhood["entities"]
        assert "Redis" in neighborhood["entities"]
        assert "Python" in neighborhood["entities"]
    
    def test_stats(self):
        self.kg.add_entity("FastAPI", "FastAPI", "framework")
        self.kg.add_entity("PostgreSQL", "PostgreSQL", "database")
        self.kg.add_relation("项目", "使用", "FastAPI")
        
        stats = self.kg.get_stats()
        assert stats["entities"] >= 3
        assert stats["relations"] >= 1


class TestEntityLinker:
    def setup_method(self):
        self.kg = KnowledgeGraph("test_linker")
        self.kg.clear()
        self.kg.add_entity("FastAPI", "FastAPI", "framework")
        self.kg.add_entity("auth_module", "用户认证模块", "module")
        self.linker = EntityLinker(self.kg)
    
    def test_link_exact_match(self):
        entities = self.linker.link("用户认证模块需要使用FastAPI")
        assert len(entities) >= 1
        entity_ids = [e[0] for e in entities]
        assert "auth_module" in entity_ids
        assert "FastAPI" in entity_ids
    
    def test_link_partial_match(self):
        entities = self.linker.link("认证模块")
        assert len(entities) >= 1
        assert entities[0][0] == "auth_module"


class TestGraphRetriever:
    def setup_method(self):
        self.kg = KnowledgeGraph("test_retriever")
        self.kg.clear()
        self.kg.add_entity("auth_module", "用户认证模块", "module")
        self.kg.add_entity("FastAPI", "FastAPI", "framework")
        self.kg.add_entity("Redis", "Redis", "cache")
        self.kg.add_relation("auth_module", "使用", "FastAPI")
        self.kg.add_relation("auth_module", "使用", "Redis")
        self.retriever = GraphRetriever(self.kg)
    
    def test_retrieve(self):
        results = self.retriever.retrieve("用户认证模块", max_hops=2)
        assert len(results) >= 1


class TestHybridRetriever:
    def setup_method(self):
        self.retriever = HybridRetriever()
    
    def test_retrieve(self):
        results = self.retriever.retrieve("测试查询")
        assert "graph_results" in results
        assert "semantic_results" in results
        assert "fused_results" in results
    
    def test_get_context(self):
        context = self.retriever.get_context("测试查询")
        assert isinstance(context, str)
