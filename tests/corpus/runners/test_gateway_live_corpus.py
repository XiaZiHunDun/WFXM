"""L3 live smoke — catalog IDs from ``meta.yaml`` ``live_smoke_ids``.

Run:
  set -a && source .env && set +a
  BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
    pytest tests/corpus/runners/test_gateway_live_corpus.py -m "corpus_live and corpus_smoke" -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.gateway.message_handler import ButlerMessageHandler
from butler.report import clear_report_cache
from tests.corpus.harness.archive import append_run_record, archive_enabled, classify_fail
from tests.corpus.harness.gateway_catalog import apply_catalog_setup, catalog_by_id
from tests.corpus.harness.gateway_live import (
    assert_live_response,
    live_dimension,
    load_live_smoke_ids,
    validate_live_smoke_ids,
)
from tests.corpus.harness.gateway_meta import load_gateway_meta
from tests.test_gateway_dev_conversations import _setup_lingwen_gateway_project
from tests.test_wechat_gateway_live_smoke import _require_minimax_for_gateway


def _resolved_session_key(handler: ButlerMessageHandler, entry: dict) -> str:
    raw = entry.get("session_key") or "wechat:u1"
    chat_id = "u1"
    if raw.startswith("wechat:"):
        parts = raw.split(":")
        if len(parts) > 1 and parts[1]:
            chat_id = parts[1]
    return handler.resolve_session_key(
        session_key=raw,
        platform="wechat",
        external_id=chat_id,
    )


@pytest.fixture
def lingwen_gateway_live(tmp_path, monkeypatch, tmp_butler_home):
    from tests.test_gateway_handler import _reset_singletons

    clear_report_cache()
    proj = _setup_lingwen_gateway_project(tmp_path, monkeypatch)
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "u1")
    monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "0")
    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat",
        chat_id="u1",
        name="灵文1号",
    )
    return handler, proj


@pytest.mark.corpus
@pytest.mark.corpus_live
@pytest.mark.corpus_smoke
@pytest.mark.live_llm
class TestGatewayLiveCorpusSmoke:
    @pytest.fixture(autouse=True)
    def _require_live_api(self):
        _require_minimax_for_gateway()

    def test_live_smoke_ids_valid(self):
        assert load_gateway_meta().get("suite_id") == "wechat_real.lw_real"
        errors = validate_live_smoke_ids()
        assert not errors, errors
        assert len(load_live_smoke_ids()) >= 5

    @pytest.mark.parametrize("catalog_id", load_live_smoke_ids())
    def test_live_catalog_smoke(self, catalog_id, lingwen_gateway_live):
        entry = catalog_by_id()[catalog_id]
        handler, proj = lingwen_gateway_live
        sk = _resolved_session_key(handler, entry)

        helpers = {
            "HELLO_REL": "docs/test_hello.txt",
            "HELLO_CONTENT": "test\n",
            "delegate_create_hello_script": lambda: [],
            "bind_script": lambda script: None,
        }
        if entry.get("setup"):
            apply_catalog_setup(
                entry,
                handler=handler,
                proj=proj,
                session_key=sk,
                helpers=helpers,
            )

        suite_id = "wechat_real.lw_real"
        model = ""
        status = "completed"
        kw_err: str | None = None
        out = ""
        passed = False

        try:
            with patch("butler.session.lifecycle.sync_turn_memory", return_value={}):
                out = handler.handle_message(
                    entry["user"],
                    session_key=sk,
                    platform="wechat",
                )
            if not isinstance(out, str):
                out = str(out)
            assert_live_response(entry, out=out)
            passed = True
        except AssertionError as exc:
            passed = False
            kw_err = str(exc)
            raise
        finally:
            if archive_enabled():
                from butler.config import get_butler_settings

                mc = get_butler_settings().get_model_config("butler")
                model = f"{mc.provider}/{mc.model}"
            append_run_record(
                suite_id=suite_id,
                case_id=catalog_id,
                dimension=live_dimension(entry),
                status="passed" if passed else "failed",
                fail_type=classify_fail(
                    loop_status=status,
                    passed=passed,
                    keyword_error=kw_err,
                ),
                model=model,
                loop_status=status,
                response_excerpt=out,
            )
