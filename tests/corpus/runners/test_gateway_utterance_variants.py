"""Variant utterance sampling — one口语变体 per strict parent (phase 2).

Run:
  PYTHONPATH=. pytest tests/corpus/runners/test_gateway_utterance_variants.py -q
"""

from __future__ import annotations

import pytest

from tests.corpus.conftest_gateway import extended_catalog_setup as _extended_setup
from tests.corpus.harness.gateway_catalog import (
    assert_expectations,
    run_catalog_turn,
    variant_catalog_by_id,
)
from tests.corpus.harness.gateway_meta import variant_sample_ids


@pytest.mark.integration
@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestGatewayUtteranceVariants:
    @pytest.mark.parametrize("variant_id", variant_sample_ids())
    def test_variant_entry(self, variant_id, catalog_handlers, patch_llm):
        entry = variant_catalog_by_id()[variant_id]
        fixture_name = entry.get("fixture", "lingwen")
        handler, proj = catalog_handlers[fixture_name]
        helpers = catalog_handlers["helpers"]

        sk = _extended_setup(
            entry,
            handler=handler,
            proj=proj,
            helpers=helpers,
            patch_llm=patch_llm,
        )

        out, tool_names, llm_called = run_catalog_turn(
            entry,
            handler=handler,
            session_key=sk,
            proj=proj,
            helpers=helpers,
            patch_llm=patch_llm,
        )
        assert_expectations(
            entry,
            out=out,
            tool_names=tool_names,
            proj=proj,
            llm_called=llm_called,
        )
