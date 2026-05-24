"""Multi-turn WeChat gateway scenarios from utterance_multiturn_catalog.yaml."""

from __future__ import annotations

import pytest

from tests.corpus.conftest_gateway import (
    extended_catalog_setup as _extended_setup,
    resolved_session_key as _resolved_session_key,
)
from tests.corpus.harness.gateway_catalog import (
    apply_catalog_setup,
    assert_expectations,
    load_multiturn_catalog,
    parametrized_multiturn_ids,
    run_catalog_turn,
)
from tests.corpus.harness.gateway_scripts import pad_script
from tests.test_gateway_dev_conversations import _bind_llm_script


def _multiturn_by_id() -> dict[str, dict]:
    return {row["id"]: row for row in load_multiturn_catalog()}


def _run_turn(
    turn: dict,
    *,
    chain_id: str,
    turn_idx: int,
    handler,
    proj,
    sk: str,
    helpers: dict,
    patch_llm,
) -> None:
    turn_id = f"{chain_id}:T{turn_idx}"
    entry = {**turn, "id": turn_id}
    mock_complete, mock_stream = patch_llm
    if turn.get("session_key"):
        sk = handler.resolve_session_key(
            session_key=turn["session_key"],
            platform="wechat",
            external_id=turn["session_key"].split(":")[-1] or "u1",
        )

    if turn.get("setup"):
        apply_catalog_setup(
            entry,
            handler=handler,
            proj=proj,
            session_key=sk,
            helpers={
                **helpers,
                "bind_script": lambda script: _bind_llm_script(
                    mock_complete, mock_stream, pad_script(script)
                ),
            },
        )

    out, tool_names, llm_called = run_catalog_turn(
        entry,
        handler=handler,
        session_key=sk,
        proj=proj,
        helpers=helpers,
        patch_llm=patch_llm,
        external_id="u1",
    )
    assert_expectations(entry, out=out, tool_names=tool_names, proj=proj, llm_called=llm_called)


@pytest.mark.integration
@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestGatewayMultiturnCatalog:
    @pytest.mark.parametrize("chain_id", parametrized_multiturn_ids())
    def test_multiturn_chain(self, chain_id, catalog_handlers, patch_llm):
        chain = _multiturn_by_id()[chain_id]
        fixture_name = chain.get("fixture", "lingwen")
        handler, proj = catalog_handlers[fixture_name]
        helpers = catalog_handlers["helpers"]
        sk = _resolved_session_key(handler, {"session_key": "wechat:u1"})

        if chain.get("setup"):
            _extended_setup(
                {"setup": chain["setup"], "id": chain_id},
                handler=handler,
                proj=proj,
                helpers=helpers,
                patch_llm=patch_llm,
            )

        for idx, turn in enumerate(chain.get("turns") or [], start=1):
            _run_turn(
                turn,
                chain_id=chain_id,
                turn_idx=idx,
                handler=handler,
                proj=proj,
                sk=sk,
                helpers=helpers,
                patch_llm=patch_llm,
            )
