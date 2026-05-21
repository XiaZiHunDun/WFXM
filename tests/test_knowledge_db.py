"""Project knowledge.db mirrors facts.json."""

from pathlib import Path

from butler.memory.knowledge_db import ProjectKnowledgeDb, sync_facts_json_to_knowledge_db


def test_sync_facts_json_to_knowledge_db(tmp_path):
    mem = tmp_path / ".butler" / "memory"
    mem.mkdir(parents=True)
    facts_path = mem / "facts.json"
    facts_path.write_text(
        '{"build_system": "python", "frameworks": ["FastAPI"]}',
        encoding="utf-8",
    )
    n = sync_facts_json_to_knowledge_db(facts_path)
    assert n >= 2
    db = ProjectKnowledgeDb(ProjectKnowledgeDb.path_for_memory_dir(mem))
    assert db.count_keys() == n
