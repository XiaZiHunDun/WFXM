"""Variant utterance sampling — one口语变体 per strict parent (phase 2).

Run:
  PYTHONPATH=. pytest tests/corpus/runners/test_gateway_utterance_variants.py -q
"""

from __future__ import annotations

pytest_plugins = ["tests.corpus.runners.test_gateway_utterance_catalog"]

from unittest.mock import MagicMock, patch

import pytest

from butler.core.agent_loop import LoopResult, LoopStatus
from tests.corpus.harness.gateway_catalog import assert_expectations, variant_catalog_by_id
from tests.corpus.harness.gateway_meta import variant_sample_ids
from tests.corpus.harness.gateway_scripts import (
    final_text_from_script,
    needs_real_tools,
    pad_script,
    script_profiles,
)
from tests.corpus.conftest_gateway import extended_catalog_setup as _extended_setup
from tests.test_gateway_acceptance import LLM_PATCH
from tests.test_gateway_dev_conversations import _bind_llm_script


@pytest.mark.integration
@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestGatewayUtteranceVariants:
    @pytest.mark.parametrize("variant_id", variant_sample_ids())
    def test_variant_entry(
        self,
        variant_id: str,
        catalog_handlers,
        patch_llm,
    ):
        entry = variant_catalog_by_id()[variant_id]
        fixture_name = entry.get("fixture", "lingwen")
        handler, proj = catalog_handlers[fixture_name]
        helpers = catalog_handlers["helpers"]
        mock_complete, mock_stream = patch_llm

        sk = _extended_setup(
            entry,
            handler=handler,
            proj=proj,
            helpers=helpers,
            patch_llm=patch_llm,
        )

        kind = entry.get("kind", "command")
        tool_names = None
        llm_called = None

        if kind in ("command", "detail"):
            with patch.object(handler, "_get_or_create_loop") as mock_loop:
                out = handler.handle_message(
                    entry["user"],
                    session_key=sk,
                    platform="wechat",
                )
                llm_called = mock_loop.called
            if not isinstance(out, str):
                out = str(out)
        elif kind == "llm":
            script_name = entry.get("script")
            script = script_profiles().get(script_name or "")
            assert script, f"{variant_id}: unknown script {script_name!r}"
            expect = entry.get("expect") or {}

            if needs_real_tools(expect):
                _bind_llm_script(mock_complete, mock_stream, pad_script(script))
                from butler.tools.registry import dispatch_tool

                with patch(
                    "butler.gateway.message_handler.dispatch_tool",
                    wraps=dispatch_tool,
                ) as spy:
                    out = handler.handle_message(
                        entry["user"],
                        session_key=sk,
                        platform="wechat",
                    )
                    tool_names = [c[0][0] for c in spy.call_args_list if c[0]]
                llm_called = True
            else:
                with patch.object(handler, "_get_or_create_loop") as mock_get:
                    loop = MagicMock()
                    loop.run.return_value = LoopResult(
                        status=LoopStatus.COMPLETED,
                        final_response=final_text_from_script(script),
                    )
                    mock_get.return_value = loop
                    out = handler.handle_message(
                        entry["user"],
                        session_key=sk,
                        platform="wechat",
                    )
                    llm_called = mock_get.called
        else:
            pytest.fail(f"{variant_id}: unsupported kind {kind!r}")

        assert_expectations(
            entry,
            out=out,
            tool_names=tool_names,
            proj=proj,
            llm_called=llm_called,
        )

    def test_variant_sample_count(self):
        ids = variant_sample_ids()
        assert len(ids) >= 30, f"expected >=30 variant samples, got {len(ids)}"
