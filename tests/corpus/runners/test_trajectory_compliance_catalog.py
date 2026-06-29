"""TCR subset: production strict utterance catalog only (AP-2)."""

from __future__ import annotations

import pytest

from tests.corpus.conftest_gateway import extended_catalog_setup as _extended_setup
from tests.corpus.harness.gateway_catalog import (
    _is_executable_row,
    assert_expectations,
    load_production_strict_catalog,
    run_catalog_turn,
)


def _strict_production_ids() -> list[str]:
    rows = load_production_strict_catalog()
    return [row["id"] for row in rows if _is_executable_row(row)]


def _catalog_by_id() -> dict[str, dict]:
    return {row["id"]: row for row in load_production_strict_catalog()}


@pytest.mark.integration
@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestTrajectoryComplianceCatalog:
    @pytest.mark.parametrize("catalog_id", _strict_production_ids())
    def test_strict_production_entry(self, catalog_id, catalog_handlers, patch_llm):
        entry = _catalog_by_id()[catalog_id]
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
