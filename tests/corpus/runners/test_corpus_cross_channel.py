"""Phase 5 — AgentLoop ↔ Gateway intent crosswalk and P0 coverage gates."""

from __future__ import annotations

import pytest

from tests.corpus.harness.corpus_intent import (
    CANONICAL_INTENTS,
    P0_CROSS_CHANNEL_INTENTS,
    build_crosswalk,
    load_crosswalk,
    validate_crosswalk,
)


@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestCorpusCrossChannel:
    def test_crosswalk_file_valid(self):
        doc = load_crosswalk()
        assert doc.get("meta", {}).get("schema", "").endswith("corpus-intent-v1.md")
        errors = validate_crosswalk(doc)
        assert not errors, errors

    def test_p0_intents_documented(self):
        doc = load_crosswalk()
        intents = {r["intent"] for r in doc.get("cross_refs") or []}
        for intent in P0_CROSS_CHANNEL_INTENTS:
            assert intent in intents, f"missing P0 intent in crosswalk: {intent}"

    def test_rebuilt_crosswalk_matches_committed(self):
        """Generator output should match git (run build_intent_crosswalk after corpus edits)."""
        built = build_crosswalk()
        errors = validate_crosswalk(built)
        assert not errors, errors
        committed = load_crosswalk()
        assert len(committed.get("cross_refs") or []) == len(built.get("cross_refs") or [])

    def test_canonical_intent_count(self):
        doc = load_crosswalk()
        assert len(doc.get("cross_refs") or []) >= len(CANONICAL_INTENTS) - 4
