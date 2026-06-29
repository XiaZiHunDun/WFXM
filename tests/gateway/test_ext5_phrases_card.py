"""EXT-5 话术卡 — 路由与短语 SSOT 单测（无 LLM / 无 iLink）。"""

from __future__ import annotations

import pytest

from butler.gateway.ext5_phrases import (
    EXT5_PHRASE_CASES,
    FIXTURE_REL,
    PHRASE_REFERENCE_BOOK,
    PHRASE_TXT_TO_MD,
    PHRASE_TXT_TO_MD_INGEST,
)


@pytest.mark.unit
class TestExt5PhrasesCard:
    def test_phrase_cases_cover_card_ids(self):
        ids = {case_id for case_id, _ in EXT5_PHRASE_CASES}
        assert ids == {
            "switch",
            "diag",
            "txt_to_md",
            "txt_to_md_ingest",
            "reference_book",
        }

    def test_fixture_path_is_project_relative(self):
        assert FIXTURE_REL == "docs/ext5-fixture-sample.txt"
        assert FIXTURE_REL in PHRASE_TXT_TO_MD
        assert FIXTURE_REL in PHRASE_TXT_TO_MD_INGEST
        assert FIXTURE_REL in PHRASE_REFERENCE_BOOK

    def test_txt_to_md_does_not_trigger_ingest_expansion(self):
        from butler.gateway.owner_ingest_shortcuts import (
            looks_owner_ingest_intent,
            try_expand_owner_ingest_phrase,
        )

        assert not looks_owner_ingest_intent(PHRASE_TXT_TO_MD)
        assert try_expand_owner_ingest_phrase(PHRASE_TXT_TO_MD, project_name="灵文1号") is None

    def test_txt_to_md_ingest_expands_to_mcp_path(self):
        from butler.gateway.owner_ingest_shortcuts import try_expand_owner_ingest_phrase

        out = try_expand_owner_ingest_phrase(
            PHRASE_TXT_TO_MD_INGEST,
            project_name="灵文1号",
            workspace="/tmp/LingWen1",
        )
        assert out
        assert "mcp_markitdown_convert_to_markdown" in out
        assert ".butler/ingest/docs/ext5-fixture-sample.md" in out

    def test_reference_book_phrase_uses_in_project_path(self):
        assert "参考书" in PHRASE_REFERENCE_BOOK
        assert "docs/ext5-fixture-sample" in PHRASE_REFERENCE_BOOK
        assert "tests/fixtures" not in PHRASE_REFERENCE_BOOK
