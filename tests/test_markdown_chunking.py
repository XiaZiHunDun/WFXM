"""PR4: Markdown hierarchical chunking and structured retrieval metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.config import reload_butler_settings
from butler.memory.chunking import (
    chunk_markdown_hierarchical,
    discover_markdown_files,
    format_chunk_embedding_text,
    heading_boost_factor,
    index_markdown_file,
    markdown_chunking_enabled,
    parse_chunk_metadata,
)
from butler.memory.search_result import enrich_search_hit, source_path_for_hit


SAMPLE_MD = """# Root

## Architecture

First paragraph about gateway.

### API

Endpoint details here.

## Decisions

- [2026-05-01] Use sqlite for vectors
"""


@pytest.mark.module_test
def test_chunk_markdown_hierarchical_splits_headings():
    chunks = chunk_markdown_hierarchical(
        SAMPLE_MD,
        rel_path="DESIGN.md",
        project_name="demo",
        min_chars=20,
        max_chars=2000,
    )
    assert len(chunks) >= 2
    paths = [" > ".join(c.heading_path) for c in chunks if c.heading_path]
    assert any("Architecture" in p for p in paths)
    assert any("API" in p for p in paths or [])


@pytest.mark.module_test
def test_chunk_source_id_and_parent():
    chunks = chunk_markdown_hierarchical(
        "## Only\n\nBody text.",
        rel_path="docs/guide.md",
        project_name="demo",
        min_chars=10,
        max_chars=500,
    )
    assert chunks
    ch = chunks[0]
    assert ch.parent_doc_id == "demo:md:docs/guide.md"
    assert ":md:docs/guide.md#h" in ch.source_id
    text = format_chunk_embedding_text(ch)
    assert "[headings:" in text
    assert "[parent:" in text


@pytest.mark.module_test
def test_heading_boost_factor():
    content = format_chunk_embedding_text(
        chunk_markdown_hierarchical(
            "## Gateway\n\nWeChat ilink gateway.",
            rel_path="MEMORY.md",
            project_name="demo",
            min_chars=5,
            max_chars=500,
        )[0]
    )
    assert heading_boost_factor(content, "gateway wechat") > 1.0
    assert heading_boost_factor(content, "unrelated xyz") == 1.0


@pytest.mark.module_test
def test_enrich_search_hit_parses_doc_metadata():
    hit = enrich_search_hit(
        {
            "source": "project_memory",
            "source_id": "demo:md:DESIGN.md#harchitecture:0000",
            "project": "demo",
            "content": (
                "[doc: DESIGN.md]\n[headings: Architecture > API]\n"
                "[parent: demo:md:DESIGN.md]\n\nBody"
            ),
            "score": 0.8,
        },
        project_workspace=Path("/tmp/proj"),
    )
    assert hit["chunk_id"].startswith("project_memory:")
    assert hit["heading_path"] == "Architecture > API"
    assert hit["parent_source_id"] == "demo:md:DESIGN.md"
    assert "DESIGN.md" in hit["source_path"] or "doc" in hit["source_path"]


@pytest.mark.module_test
def test_index_markdown_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "bh"))
    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
    reload_butler_settings()
    proj_dir = tmp_path / "MyProj"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        "name: MyProj\nworkspace: .\n",
        encoding="utf-8",
    )
    (proj_dir / "DESIGN.md").write_text(SAMPLE_MD, encoding="utf-8")

    from butler.memory.butler_memory import ButlerMemory

    bm = ButlerMemory(tmp_path / "bh", tenant_id="default")
    assert bm.semantic is not None
    n = index_markdown_file(
        bm.semantic,
        project_name="MyProj",
        file_path=proj_dir / "DESIGN.md",
        project_dir=proj_dir,
        workspace=proj_dir,
    )
    assert n >= 1
    assert bm.semantic.count_rows() >= n


@pytest.mark.module_test
def test_discover_markdown_files(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_MARKDOWN_INDEX_PATHS", "DESIGN.md,docs/**/*.md")
    proj = tmp_path / "P"
    proj.mkdir()
    (proj / "DESIGN.md").write_text("# D\n", encoding="utf-8")
    (proj / "docs").mkdir()
    (proj / "docs" / "a.md").write_text("# A\n", encoding="utf-8")
    found = discover_markdown_files(proj, proj)
    names = {p.name for p in found}
    assert "DESIGN.md" in names
    assert "a.md" in names


@pytest.mark.module_test
def test_markdown_chunking_enabled_default():
    assert markdown_chunking_enabled() is True


@pytest.mark.module_test
def test_discover_markdown_files_ingest_pilot_dirs(tmp_path):
    ws = tmp_path / "proj"
    refs = ws / "novel-factory" / "references"
    refs.mkdir(parents=True)
    (refs / "canon.md").write_text("# Canon\n", encoding="utf-8")
    (ws / "stack.yaml").write_text(
        "ingest_pilot_dirs:\n  - novel-factory/references\n",
        encoding="utf-8",
    )
    found = discover_markdown_files(ws, ws)
    assert any(p.name == "canon.md" for p in found)
