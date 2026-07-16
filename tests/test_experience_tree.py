"""Experience Tree Tests — validate domain routing, retrieval, writing, and management."""

import os
import tempfile
import pytest

from butler.memory.experience.store import ExperienceStore, ExperienceNode
from butler.memory.experience.domain_router import DomainRouter
from butler.memory.experience.classifier import DomainClassifier
from butler.memory.experience.retriever import ExperienceRetriever
from butler.memory.experience.writer import ExperienceWriter
from butler.memory.experience.tree import ExperienceTree
from butler.memory.experience.taxonomy import DOMAINS, CATEGORIES


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_exp.db")
        yield ExperienceStore(db_path=db_path)


@pytest.fixture
def tree(store):
    return ExperienceTree(store=store)


class TestTaxonomy:
    def test_domains_defined(self):
        assert len(DOMAINS) == 8
        assert "daily_life" in DOMAINS
        assert "agent_dev" in DOMAINS
        assert "database" in DOMAINS
        assert "llm_usage" in DOMAINS
        assert "network_info" in DOMAINS
        assert "dev_ops" in DOMAINS
        assert "code_engineering" in DOMAINS
        assert "project_mgmt" in DOMAINS

    def test_categories_defined(self):
        assert len(CATEGORIES) == 8
        assert "skills" in CATEGORIES
        assert "tools" in CATEGORIES
        assert "mcp" in CATEGORIES
        assert "workflows" in CATEGORIES
        assert "user_profile" in CATEGORIES
        assert "local_products" in CATEGORIES
        assert "recent_conversations" in CATEGORIES
        assert "knowledge_facts" in CATEGORIES

    def test_each_domain_has_keywords(self):
        for did, d in DOMAINS.items():
            assert len(d["keywords"]) > 0, f"{did} has no keywords"


class TestDomainRouter:
    def test_route_agent_dev(self):
        router = DomainRouter()
        domain, confidence = router.route("如何开发一个 agent loop?")
        assert domain == "agent_dev"
        assert confidence > 0

    def test_route_database(self):
        router = DomainRouter()
        domain, confidence = router.route("PostgreSQL 创建 JSONB 索引")
        assert domain == "database"
        assert confidence > 0

    def test_route_llm_usage(self):
        router = DomainRouter()
        domain, confidence = router.route("DeepSeek API 调用 token 限制")
        assert domain == "llm_usage"
        assert confidence > 0

    def test_route_network_info(self):
        router = DomainRouter()
        domain, confidence = router.route("搜索 FastAPI 官方文档")
        assert domain == "network_info"
        assert confidence > 0

    def test_route_dev_ops(self):
        router = DomainRouter()
        domain, confidence = router.route("Docker 构建镜像并部署")
        assert domain == "dev_ops"
        assert confidence > 0

    def test_route_code_engineering(self):
        router = DomainRouter()
        domain, confidence = router.route("重构代码并添加 pytest 测试")
        assert domain == "code_engineering"
        assert confidence > 0

    def test_route_multi(self):
        router = DomainRouter()
        results = router.route_multi("用 Docker 部署 PostgreSQL 数据库")
        assert len(results) >= 1
        domains = [r[0] for r in results]
        assert "database" in domains or "dev_ops" in domains

    def test_empty_query(self):
        router = DomainRouter()
        domain, confidence = router.route("")
        assert domain == "daily_life"
        assert confidence == 0.0

    def test_frequency_weighting(self):
        router = DomainRouter()
        router.record_hit("database")
        router.record_hit("database")
        domain, conf_after = router.route("PostgreSQL query")
        assert domain == "database"


class TestDomainClassifier:
    def test_classify_tool_usage(self):
        classifier = DomainClassifier()
        domain, category, conf = classifier.classify(
            "用 terminal 执行 psql 查询",
            "查询成功",
            {"tool_name": "terminal"},
        )
        assert category == "tools"

    def test_classify_skill_usage(self):
        classifier = DomainClassifier()
        domain, category, conf = classifier.classify(
            "使用 ReAct 技能进行推理",
            "推理完成",
            {"skill_name": "react"},
        )
        assert category == "skills"

    def test_classify_knowledge_fact(self):
        classifier = DomainClassifier()
        domain, category, conf = classifier.classify(
            "PostgreSQL JSONB 查询应该使用 GIN 索引，这是最佳实践",
        )
        assert domain == "database"
        assert conf > 0

    def test_classify_local_product(self):
        classifier = DomainClassifier()
        domain, category, conf = classifier.classify(
            "Redis 缓存已接入，端口 6379",
            metadata={"product_name": "redis"},
        )
        assert category == "local_products"


class TestExperienceStore:
    def test_save_and_get_node(self, store):
        node = ExperienceNode(
            node_id="test/node/test_node",
            domain="agent_dev",
            category="tools",
            name="test_node",
            content="测试经验内容",
        )
        store.save_node(node)

        loaded = store.get_node("test/node/test_node")
        assert loaded is not None
        assert loaded.name == "test_node"
        assert loaded.content == "测试经验内容"

    def test_search_by_domain(self, store):
        for i in range(3):
            node = ExperienceNode(
                node_id=f"agent_dev/tools/tool_{i}",
                domain="agent_dev",
                category="tools",
                name=f"tool_{i}",
                content=f"工具 {i} 的使用经验",
            )
            store.save_node(node)

        results = store.search_by_domain("agent_dev", limit=10)
        assert len(results) == 3

    def test_search_fts(self, store):
        node = ExperienceNode(
            node_id="database/knowledge_facts/jsonb_index",
            domain="database",
            category="knowledge_facts",
            name="jsonb_index",
            content="PostgreSQL JSONB 查询使用 GIN 索引",
        )
        store.save_node(node)

        results = store.search_fts("JSONB")
        assert len(results) >= 1

    def test_increment_hit(self, store):
        node = ExperienceNode(
            node_id="test/tools/hit_test",
            domain="agent_dev",
            category="tools",
            name="hit_test",
            content="hit test",
        )
        store.save_node(node)

        store.increment_hit("test/tools/hit_test", success=True)
        store.increment_hit("test/tools/hit_test", success=True)

        loaded = store.get_node("test/tools/hit_test")
        assert loaded.hit_count == 2
        assert loaded.success_count == 2
        assert loaded.success_rate == 1.0

    def test_add_and_get_links(self, store):
        for nid in ["a/1", "a/2", "a/3"]:
            store.save_node(ExperienceNode(
                node_id=nid, domain="agent_dev", category="tools", name=nid
            ))

        store.add_link("a/1", "a/2", "depends_on")
        store.add_link("a/1", "a/3", "related_to")

        links = store.get_linked_nodes("a/1")
        assert len(links) == 2

        dep_links = store.get_linked_nodes("a/1", relation="depends_on")
        assert len(dep_links) == 1
        assert dep_links[0] == "a/2"

    def test_domain_stats(self, store):
        store.save_node(ExperienceNode(
            node_id="db/1", domain="database", category="tools", name="t1"
        ))
        store.save_node(ExperienceNode(
            node_id="db/2", domain="database", category="skills", name="s1"
        ))

        stats = store.get_domain_stats("database")
        assert stats["total_nodes"] == 2

    def test_delete_node(self, store):
        store.save_node(ExperienceNode(
            node_id="del/1", domain="agent_dev", category="tools", name="del"
        ))
        assert store.delete_node("del/1")
        assert store.get_node("del/1") is None


class TestExperienceTree:
    def test_write_and_retrieve(self, tree):
        node_id = tree.write(
            "如何使用 FastAPI 实现用户认证?",
            "使用 FastAPI 的 Security 模块，配合 JWT token",
            {"tool_name": "read_file"},
        )
        assert node_id

        hits = tree.retrieve("FastAPI 用户认证")
        assert len(hits) >= 1

    def test_write_multiple_domains(self, tree):
        tree.write("Docker 构建镜像", "docker build -t app .", {})
        tree.write("PostgreSQL 查询优化", "使用 EXPLAIN ANALYZE", {})
        tree.write("pytest 添加测试", "pytest -v tests/", {})

        hits = tree.retrieve("Docker 部署")
        assert len(hits) >= 1

    def test_get_all_stats(self, tree):
        tree.write("agent loop 开发", "使用 ReAct 模式", {})
        stats = tree.get_all_stats()
        assert "total_nodes" in stats
        assert stats["total_nodes"] >= 1

    def test_format_tree(self, tree):
        tree.write("FastAPI 认证", "JWT + OAuth2", {})
        formatted = tree.format_tree()
        assert "experience_tree/" in formatted
        assert "agent_dev" in formatted or "database" in formatted

    def test_link_experiences(self, tree):
        id1 = tree.write("PostgreSQL 索引", "GIN 索引", {})
        id2 = tree.write("PostgreSQL 查询优化", "EXPLAIN ANALYZE", {})
        tree.link_experience(id1, id2, "related_to")

        links = tree._store.get_linked_nodes(id1)
        assert id2 in links

    def test_retrieve_low_confidence(self, tree):
        """When query doesn't match any domain well, should still return something."""
        hits = tree.retrieve("xyz random unknown topic")
        assert isinstance(hits, list)

    def test_auto_classify_on_write(self, tree):
        node_id = tree.write(
            "用 terminal 执行 psql 查询数据库",
            "psql -c 'SELECT * FROM users'",
            {"tool_name": "terminal"},
        )
        node = tree.get_node(node_id)
        assert node is not None
        assert node.domain == "database"
        assert node.category == "tools"
