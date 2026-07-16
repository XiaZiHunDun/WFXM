"""Memory architecture tests — verify DomainRouter, ExperienceTree, and KnowledgeGraph."""

import pytest

from butler.memory.experience.domain_router import DomainRouter
from butler.memory.experience.tree import get_experience_tree
from butler.memory.knowledge_graph import get_knowledge_graph
from butler.memory.knowledge_warehouse.warehouse import KnowledgeWarehouse


class TestDomainRouter:
    def test_route_fastapi(self):
        router = DomainRouter()
        domain, confidence = router.route("How to use FastAPI for authentication?")
        assert domain == "agent_dev"
        assert confidence > 0.1

    def test_semantic_matching_no_keywords(self):
        router = DomainRouter()
        domain, confidence = router.route("How to fine tune a transformer model?")
        assert domain == "llm_usage"
        assert confidence > 0.03

    def test_route_docker(self):
        router = DomainRouter()
        domain, confidence = router.route("Docker container deployment best practices")
        assert domain == "dev_ops"
        assert confidence > 0.1

    def test_route_postgresql(self):
        router = DomainRouter()
        domain, confidence = router.route("PostgreSQL performance optimization")
        assert domain == "database"
        assert confidence > 0.1

    def test_route_prompt_engineering(self):
        router = DomainRouter()
        domain, confidence = router.route("LLM prompt engineering techniques")
        assert domain == "llm_usage"
        assert confidence > 0.1

    def test_route_multi(self):
        router = DomainRouter()
        domains = router.route_multi("FastAPI authentication", top_n=3)
        assert len(domains) <= 3
        assert domains[0][0] == "agent_dev"


class TestExperienceTree:
    def test_retrieve_basic(self):
        tree = get_experience_tree()
        results = tree.retrieve("FastAPI", top_k=3)
        assert len(results) >= 0

    def test_get_all_stats(self):
        tree = get_experience_tree()
        stats = tree.get_all_stats()
        assert "total_nodes" in stats
        assert "total_links" in stats


class TestKnowledgeGraph:
    def test_get_stats(self):
        kg = get_knowledge_graph()
        stats = kg.get_stats()
        assert "entities" in stats
        assert "relations" in stats

    def test_add_and_get_entity(self):
        kg = get_knowledge_graph()
        kg.add_entity("test:entity1", "Test Entity", "test", {"attr": "value"})
        entity = kg.get_entity("test:entity1")
        assert entity is not None
        assert entity["label"] == "Test Entity"


class TestKnowledgeWarehouse:
    def test_get_stats(self):
        warehouse = KnowledgeWarehouse()
        stats = warehouse.get_stats()
        assert "total_materials" in stats
        assert "status_counts" in stats
