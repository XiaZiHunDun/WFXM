"""v1-only: DA-01 代码生成应委派 dev，Lead 不直接 write_file。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.tools.registry import dispatch_tool
from tests.corpus.harness.registry import get_suite, load_suite_corpus
from tests.gateway.test_gateway_acceptance import _text_response, _tool_response
from tests.gateway.test_gateway_dev_conversations import _bind_llm_script


@pytest.mark.corpus
@pytest.mark.corpus_mock
@pytest.mark.module_test
class TestDevAssistantV1ButlerLead:
    def test_da01_lead_should_delegate_not_write(self, lingwen_handler, patch_llm):
        handler, _proj = lingwen_handler
        corpus, _ = load_suite_corpus(get_suite("dev_assistant.v1"))
        case = next(c for c in corpus["cases"] if c["id"] == "DA-01")
        mock_complete, mock_stream = patch_llm
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _tool_response(
                    "delegate_task",
                    {"role": "dev", "task": "编写读取 sales.csv 计算 amount 列总和的 Python 函数"},
                ),
                _text_response("已创建 sales 读取函数"),
                _text_response("已委派开发代理完成代码任务"),
            ],
        )

        with patch(
            "butler.gateway.message_handler.dispatch_tool",
            wraps=dispatch_tool,
        ) as spy:
            handler.handle_message(
                case["user"].strip(),
                session_key="wechat:u1",
                platform="wechat",
            )
            names = [c[0][0] for c in spy.call_args_list if c[0]]

        assert "delegate_task" in names
        assert "write_file" not in names


@pytest.fixture
def lingwen_handler(tmp_path, monkeypatch, tmp_butler_home):
    from butler.gateway.message_handler import ButlerMessageHandler
    from butler.report import clear_report_cache
    from tests.gateway.test_gateway_dev_conversations import _setup_lingwen_gateway_project
    from tests.gateway.test_gateway_handler import _reset_singletons

    clear_report_cache()
    _setup_lingwen_gateway_project(tmp_path, monkeypatch)
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat",
        chat_id="u1",
        name="灵文1号",
    )
    return handler, None


@pytest.fixture
def patch_llm(mock_llm_response):
    from tests.gateway.test_gateway_acceptance import LLM_PATCH
    from unittest.mock import patch

    with (
        patch(f"{LLM_PATCH}.complete") as mock_complete,
        patch(f"{LLM_PATCH}.stream") as mock_stream,
    ):
        default = mock_llm_response()
        mock_complete.return_value = default
        mock_stream.return_value = default
        yield mock_complete, mock_stream
