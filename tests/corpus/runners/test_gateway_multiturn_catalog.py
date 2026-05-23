"""Multi-turn WeChat gateway scenarios from utterance_multiturn_catalog.yaml."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.gateway.message_handler import ButlerMessageHandler
from butler.report import clear_report_cache
from tests.corpus.harness.gateway_catalog import (
    apply_catalog_setup,
    assert_expectations,
    load_multiturn_catalog,
    parametrized_multiturn_ids,
)
from tests.corpus.harness.gateway_scripts import (
    final_text_from_script,
    needs_real_tools,
    pad_script,
    script_profiles,
)
from tests.corpus.conftest_gateway import (
    extended_catalog_setup as _extended_setup,
    resolved_session_key as _resolved_session_key,
)
from tests.test_gateway_dev_conversations import (
    _bind_llm_script,
    _delegate_create_py_script,
    _delegate_create_hello_script,
    _delegate_delete_both_script,
    _setup_dual_gateway_projects,
    _setup_lingwen_gateway_project,
)
from tests.test_gateway_handler import _reset_singletons


def _multiturn_by_id() -> dict[str, dict]:
    return {row["id"]: row for row in load_multiturn_catalog()}


def _run_turn(
    turn: dict,
    *,
    chain_id: str,
    turn_idx: int,
    handler: ButlerMessageHandler,
    proj: Path,
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

    kind = turn.get("kind", "command")
    tool_names = None
    llm_called = None

    if kind in ("command", "detail"):
        with patch.object(handler, "_get_or_create_loop") as mock_loop:
            out = handler.handle_message(
                turn["user"], session_key=sk, platform="wechat", external_id="u1"
            )
            llm_called = mock_loop.called
        if not isinstance(out, str):
            out = str(out)
    elif kind == "llm":
        script_name = turn.get("script")
        script = script_profiles().get(script_name or "")
        assert script, f"{turn_id}: unknown script {script_name!r}"
        expect = turn.get("expect") or {}
        if needs_real_tools(expect):
            _bind_llm_script(mock_complete, mock_stream, pad_script(script))
            from butler.tools.registry import dispatch_tool

            with patch(
                "butler.gateway.message_handler.dispatch_tool",
                wraps=dispatch_tool,
            ) as spy:
                out = handler.handle_message(
                turn["user"], session_key=sk, platform="wechat", external_id="u1"
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
                turn["user"], session_key=sk, platform="wechat", external_id="u1"
            )
                llm_called = mock_get.called
    else:
        pytest.fail(f"{turn_id}: unsupported kind {kind!r}")

    assert_expectations(entry, out=out, tool_names=tool_names, proj=proj, llm_called=llm_called)


@pytest.fixture
def multiturn_handlers(tmp_path, monkeypatch, tmp_butler_home):
    clear_report_cache()
    _setup_dual_gateway_projects(tmp_path, monkeypatch)
    lw_proj = _setup_lingwen_gateway_project(tmp_path, monkeypatch)
    wf = lw_proj / "novel-factory" / "workflow_state.json"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text('{"phase": "draft", "step": "outline"}\n', encoding="utf-8")
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    _reset_singletons()

    dual = ButlerMessageHandler(channel="gateway")
    dual._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat", chat_id="u1", name="灵文1号",
    )
    lingwen = ButlerMessageHandler(channel="gateway")
    lingwen._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat", chat_id="u1", name="灵文1号",
    )
    from tests.test_gateway_dev_conversations import _delegate_create_hello_script

    helpers = {
        "delegate_create_hello_script": _delegate_create_hello_script,
        "delegate_create_demo_py_script": _delegate_create_py_script,
        "delegate_delete_both_script": _delegate_delete_both_script,
        "HELLO_REL": "docs/test_hello.txt",
        "HELLO_CONTENT": "莎丽委派 dev 完成\n",
    }
    return {"dual": (dual, lw_proj), "lingwen": (lingwen, lw_proj), "helpers": helpers}


@pytest.mark.integration
@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestGatewayMultiturnCatalog:
    @pytest.mark.parametrize("chain_id", parametrized_multiturn_ids())
    def test_multiturn_chain(self, chain_id, multiturn_handlers, patch_llm):
        chain = _multiturn_by_id()[chain_id]
        fixture_name = chain.get("fixture", "lingwen")
        handler, proj = multiturn_handlers[fixture_name]
        helpers = multiturn_handlers["helpers"]
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

    def test_multiturn_count(self):
        chains = load_multiturn_catalog()
        assert len(chains) >= 20
        long_chains = sum(1 for c in chains if len(c.get("turns") or []) >= 5)
        assert long_chains >= 6, f"expected >=6 chains with 5+ turns, got {long_chains}"
