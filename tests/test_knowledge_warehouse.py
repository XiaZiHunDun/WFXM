"""Knowledge Warehouse Tests — validate material ingestion and digestion."""

import os
import tempfile
import pytest

from butler.memory.knowledge_warehouse.warehouse import KnowledgeWarehouse, Material
from butler.memory.knowledge_warehouse.ingestor import MaterialIngestor
from butler.memory.knowledge_warehouse.digestion import DigestionPipeline


@pytest.fixture
def warehouse():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_kw.db")
        storage_dir = os.path.join(tmpdir, "storage")
        yield KnowledgeWarehouse(db_path=db_path, storage_dir=storage_dir)


@pytest.fixture
def ingestor(warehouse):
    return MaterialIngestor(warehouse=warehouse)


@pytest.fixture
def pipeline(warehouse):
    return DigestionPipeline(warehouse=warehouse)


class TestKnowledgeWarehouse:
    def test_add_material(self, warehouse):
        material_id, was_added = warehouse.add_material(
            domain_hint="database",
            raw_content="PostgreSQL JSONB 查询使用 GIN 索引",
            source_type="text",
            title="PostgreSQL索引技巧",
        )
        assert was_added
        assert material_id.startswith("mat_")

    def test_add_duplicate_material(self, warehouse):
        content = "test content"
        _, added1 = warehouse.add_material("test", content)
        _, added2 = warehouse.add_material("test", content)
        assert added1
        assert not added2

    def test_get_material(self, warehouse):
        mid, _ = warehouse.add_material("test", "content")
        material = warehouse.get_material(mid)
        assert material is not None
        assert material.material_id == mid
        assert material.domain_hint == "test"
        assert material.content_hash is not None

    def test_list_materials(self, warehouse):
        for i in range(3):
            warehouse.add_material(f"domain_{i}", f"content_{i}")

        materials = warehouse.list_materials(limit=10)
        assert len(materials) == 3

    def test_update_status(self, warehouse):
        mid, _ = warehouse.add_material("test", "content")
        warehouse.update_status(mid, "queued")
        material = warehouse.get_material(mid)
        assert material.status == "queued"

    def test_mark_digested(self, warehouse):
        mid, _ = warehouse.add_material("test", "content")
        warehouse.mark_digested(mid, ["exp_1", "exp_2"])
        material = warehouse.get_material(mid)
        assert material.status == "digested"
        assert "exp_1" in material.digested_experience_ids
        assert "exp_2" in material.digested_experience_ids

    def test_enqueue_and_get_queued(self, warehouse):
        mid, _ = warehouse.add_material("test", "content")
        warehouse.enqueue_for_digestion(mid)
        queued = warehouse.get_queued_materials()
        assert len(queued) == 1
        assert queued[0].material_id == mid

    def test_add_tags(self, warehouse):
        mid, _ = warehouse.add_material("test", "content")
        warehouse.add_tag(mid, "tag1")
        warehouse.add_tag(mid, "tag2")
        tags = warehouse.get_tags(mid)
        assert "tag1" in tags
        assert "tag2" in tags

    def test_get_stats(self, warehouse):
        warehouse.add_material("domain1", "content1")
        warehouse.add_material("domain1", "content2")
        warehouse.add_material("domain2", "content3")

        stats = warehouse.get_stats()
        assert stats["total_materials"] == 3
        assert stats["domain_counts"]["domain1"] == 2
        assert stats["domain_counts"]["domain2"] == 1

    def test_archive_material(self, warehouse):
        mid, _ = warehouse.add_material("test", "content")
        warehouse.archive_material(mid)
        material = warehouse.get_material(mid)
        assert material.status == "archived"

    def test_delete_material(self, warehouse):
        mid, _ = warehouse.add_material("test", "content")
        assert warehouse.delete_material(mid)
        assert warehouse.get_material(mid) is None


class TestMaterialIngestor:
    def test_ingest_text(self, ingestor):
        mid, added = ingestor.ingest_text(
            content="FastAPI is a modern web framework",
            domain_hint="agent_dev",
            title="FastAPI介绍",
        )
        assert added
        assert mid.startswith("mat_")

    def test_ingest_markdown(self, ingestor):
        mid, added = ingestor.ingest_markdown(
            content="# Test Title\n\nSome content here.",
            domain_hint="code_engineering",
        )
        assert added
        material = ingestor._warehouse.get_material(mid)
        assert "Test Title" in material.title

    def test_ingest_code(self, ingestor):
        mid, added = ingestor.ingest_code(
            code="def hello(): return 'world'",
            language="python",
            domain_hint="code_engineering",
        )
        assert added
        material = ingestor._warehouse.get_material(mid)
        assert "language" in material.metadata
        assert material.metadata["language"] == "python"

    def test_bulk_ingest(self, ingestor):
        materials = [
            {"source_type": "text", "content": "Material 1", "domain_hint": "test"},
            {"source_type": "text", "content": "Material 2", "domain_hint": "test"},
        ]
        results = ingestor.bulk_ingest(materials)
        assert len(results) == 2
        assert results[0][1]
        assert results[1][1]

        queued = ingestor._warehouse.get_queued_materials(limit=10)
        assert len(queued) == 2


class TestDigestionPipeline:
    def test_process_single(self, warehouse, pipeline):
        mid, _ = warehouse.add_material("test", "Test content")
        warehouse.enqueue_for_digestion(mid)

        success = pipeline.process_single(mid)
        assert success

        material = warehouse.get_material(mid)
        assert material.status == "digested"
        assert len(material.digested_experience_ids) >= 1

    def test_process_batch(self, warehouse, pipeline):
        for i in range(3):
            mid, _ = warehouse.add_material("test", f"Content {i}")
            warehouse.enqueue_for_digestion(mid)

        count = pipeline.process_batch(batch_size=5)
        assert count == 3

        stats = warehouse.get_stats()
        assert stats["status_counts"]["digested"] == 3

    def test_fallback_extraction(self, warehouse, pipeline):
        mid, _ = warehouse.add_material("database", "PostgreSQL索引优化技巧")
        warehouse.enqueue_for_digestion(mid)

        success = pipeline.process_single(mid)
        assert success

        material = warehouse.get_material(mid)
        assert material.status == "digested"

    def test_get_stats(self, warehouse, pipeline):
        warehouse.add_material("test", "content")
        stats = pipeline.get_stats()
        assert "warehouse" in stats
        assert "experience_tree" in stats
