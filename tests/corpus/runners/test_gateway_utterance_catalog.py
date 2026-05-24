"""Data-driven gateway tests from utterance_catalog.yaml.

Run:
  PYTHONPATH=. pytest tests/corpus/runners/test_gateway_utterance_catalog.py -q
"""

from __future__ import annotations

import pytest

from tests.corpus.conftest_gateway import extended_catalog_setup as _extended_setup
from tests.corpus.harness.gateway_catalog import (
    assert_expectations,
    catalog_by_id,
    parametrized_catalog_ids,
    run_catalog_turn,
)


@pytest.mark.integration
@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestGatewayUtteranceCatalog:
    @pytest.mark.parametrize("catalog_id", parametrized_catalog_ids())
    def test_catalog_entry(self, catalog_id, catalog_handlers, patch_llm):
        entry = catalog_by_id()[catalog_id]
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
