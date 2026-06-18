"""Owner experience seed: purge filler + pointer seeds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.memory.butler_memory import ButlerMemory
from butler.memory.owner_experience_seed import (
    purge_benchmark_filler,
    run_owner_experience_seed,
    seed_owner_experiences,
)


@pytest.fixture
def seed_json(tmp_path: Path) -> Path:
    data = [
        {
            "seed_id": "test-seed-one",
            "project": "p1",
            "category": "ops",
            "tags": ["seed:owner-experience", "tool:butler_recall"],
            "content": "测试种子经验：发版前 recall 核对。",
        }
    ]
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_purge_benchmark_filler(tmp_path):
    home = tmp_path / "butler"
    bm = ButlerMemory(home, tenant_id="default")
    bm.experience.add("bench", "cap", "capacity_benchmark_first_entry_unique")
    bm.experience.add("bench", "cap", "filler entry number 0 for capacity test")
    bm.experience.add("real", "note", "keep this row")
    bm.close()

    result = purge_benchmark_filler(home)
    assert result["deleted_sql_rows"] == 2

    bm2 = ButlerMemory(home, tenant_id="default")
    rows = bm2.experience.get_recent(limit=50)
    bm2.close()
    contents = [r.get("content") for r in rows]
    assert "keep this row" in contents
    assert not any("filler entry" in (c or "") for c in contents)


def test_seed_idempotent(tmp_path, seed_json: Path):
    home = tmp_path / "butler"
    first = seed_owner_experiences(home, seed_path=seed_json)
    second = seed_owner_experiences(home, seed_path=seed_json)
    assert first["added"] == 1
    assert second["skipped"] == 1
    assert second["added"] == 0
    assert second.get("updated", 0) == 0

    bm = ButlerMemory(home, tenant_id="default")
    assert bm.experience.has_tag_substring("seed:id:test-seed-one")
    bm.close()


def test_seed_updates_content_when_changed(tmp_path, seed_json: Path):
    home = tmp_path / "butler"
    first = seed_owner_experiences(home, seed_path=seed_json)
    assert first["added"] == 1

    data = json.loads(seed_json.read_text(encoding="utf-8"))
    data[0]["content"] = "更新后的种子经验：先 web_search 再 scrape。"
    seed_json.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    second = seed_owner_experiences(home, seed_path=seed_json)
    assert second["skipped"] == 0
    assert second["added"] == 0
    assert second["updated"] == 1

    bm = ButlerMemory(home, tenant_id="default")
    rows = bm.experience.get_recent(limit=5)
    bm.close()
    assert any("web_search" in str(r.get("content") or "") for r in rows)


def test_run_pipeline(tmp_path, seed_json: Path):
    home = tmp_path / "butler"
    bm = ButlerMemory(home, tenant_id="default")
    bm.experience.add("bench", "cap", "filler entry number 1 for capacity test")
    bm.close()

    result = run_owner_experience_seed(home, seed_path=seed_json)
    assert result["ok"] is True
    assert result["purge"]["deleted_sql_rows"] == 1
    assert result["seed"]["added"] == 1
