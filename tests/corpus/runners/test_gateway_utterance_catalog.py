"""Data-driven gateway tests from utterance_catalog.yaml.

Run:
  PYTHONPATH=. pytest tests/corpus/runners/test_gateway_utterance_catalog.py -q
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.report import get_last_report
from tests.corpus.conftest_gateway import (
    extended_catalog_setup as _extended_setup,
    resolved_session_key as _resolved_session_key,
)
from tests.corpus.harness.gateway_catalog import (
    assert_expectations,
    catalog_by_id,
    load_production_strict_catalog,
    load_reference_smoke_catalog,
    load_reference_strict_catalog,
    parametrized_catalog_ids,
)
from tests.corpus.harness.gateway_scripts import (
    final_text_from_script,
    needs_real_tools,
    pad_script,
    script_profiles,
)
from tests.test_gateway_dev_conversations import _bind_llm_script


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
        mock_complete, mock_stream = patch_llm

        sk = _extended_setup(
            entry,
            handler=handler,
            proj=proj,
            helpers=helpers,
            patch_llm=patch_llm,
        )

        kind = entry.get("kind", "command")
        tool_names: list[str] | None = None
        llm_called: bool | None = None

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
            assert script, f"{catalog_id}: unknown script {script_name!r}"
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
            pytest.fail(f"{catalog_id}: unsupported kind {kind!r}")

        assert_expectations(
            entry,
            out=out,
            tool_names=tool_names,
            proj=proj,
            llm_called=llm_called,
        )

    def test_catalog_count_meets_target(self):
        rows = parametrized_catalog_ids()
        assert len(rows) >= 200, (
            f"expected >=200 main+strict+production executable entries, got {len(rows)}"
        )

    def test_reference_smoke_inventory(self):
        smoke = load_reference_smoke_catalog()
        assert len(smoke) >= 400, f"smoke reference inventory expected >=400, got {len(smoke)}"
        assert all(r.get("runner") == "reference_smoke" for r in smoke)

    def test_reference_strict_catalog(self):
        strict = load_reference_strict_catalog()
        assert len(strict) >= 95, f"strict reference expected >=95, got {len(strict)}"
        assert all(r.get("quality") == "strict" for r in strict)
        ga = sum(1 for r in strict if r.get("script") == "generic_ack")
        assert ga <= 5, f"strict generic_ack should be <=5, got {ga}"

    def test_production_catalog(self):
        prod = load_production_strict_catalog()
        assert len(prod) >= 30, f"production expected >=30, got {len(prod)}"
        assert all(r.get("tier") == "production" for r in prod)
