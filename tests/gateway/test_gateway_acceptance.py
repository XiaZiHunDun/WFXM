"""Gateway acceptance tests mapped to docs/guides/manual-testing-guide.md §3.4–3.5.

Automated coverage for Butler-native WeChat gateway behavior. True iLink delivery
still requires manual smoke on WeChat; see §六记录表.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import link_llm_stream_mock

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.platforms.types import MessageEvent, MessageType, SessionSource
from butler.gateway.runner import _butler_message_handler
from butler.tools.registry import dispatch_tool

_REPO_ROOT = Path(__file__).resolve().parents[2]
LLM_PATCH = "butler.transport.llm_client.LLMClient"


def _text_response(content: str):
    from butler.transport.types import NormalizedResponse, Usage

    return NormalizedResponse(
        content=content,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _tool_response(name: str, args: dict, *, tool_id: str = "call_1"):
    from butler.transport.types import NormalizedResponse, Usage, build_tool_call

    return NormalizedResponse(
        tool_calls=[build_tool_call(tool_id, name, args)],
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.fixture
def patch_llm(mock_llm_response):
    with (
        patch(f"{LLM_PATCH}.complete") as mock_complete,
        patch(f"{LLM_PATCH}.stream") as mock_stream,
    ):
        default = mock_llm_response()
        mock_complete.return_value = default
        link_llm_stream_mock(mock_complete, mock_stream)
        yield mock_complete, mock_stream


@pytest.fixture
def gateway_handler(monkeypatch, tmp_path):
    from butler.report import clear_report_cache
    from tests.gateway.test_gateway_handler import _reset_singletons

    clear_report_cache()
    empty_projects = tmp_path / "empty-projects"
    empty_projects.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(empty_projects))
    # Sprint 17 SEC-11: 多数 slash 命令的 registry handler 現在有 owner gate
    # (e.g. /health, /状态, /项目). 走 dev 旁路跳过 owner 校验, 避免每个测试
    # 都要伪造 owner 身份. owner-gate 相关测试由 test_sprint17_sec11* 专门覆盖.
    monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.current_project = ""
    return handler


@pytest.fixture
def gateway_handler_with_project(tmp_path, monkeypatch, tmp_butler_home):
    from tests.gateway.test_gateway_handler import _setup_projects

    _setup_projects(tmp_path, monkeypatch)
    # Sprint 17 SEC-11: 多数 slash 命令的 registry handler 現在有 owner gate.
    # 走 dev 旁路跳过 owner 校验 (与 gateway_handler fixture 保持一致).
    monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project("test-project")
    return handler


@pytest.mark.integration
class TestManualGuide34Dialog:
    """§3.4 微信对话"""

    def test_341_greeting(self, gateway_handler, patch_llm, mock_llm_response):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = mock_llm_response(content="你好，我是莎丽。")
        mock_stream.return_value = mock_complete.return_value

        out = gateway_handler.handle_message("你好", session_key="wechat:u1", platform="wechat")

        assert "莎丽" in out or len(out) > 0
        assert "<think>" not in out

    def test_342_multi_turn_context(self, gateway_handler, patch_llm):
        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _text_response("好的，我记住了。"),
            _text_response("你叫王五。"),
        ]
        link_llm_stream_mock(mock_complete, mock_stream)

        sk = "wechat:u1"
        gateway_handler.handle_message("我叫王五", session_key=sk, platform="wechat")
        out = gateway_handler.handle_message("我叫什么？", session_key=sk, platform="wechat")

        assert "王五" in out

    def test_343_tool_read_file_line_count(self, gateway_handler, patch_llm, monkeypatch):
        monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(_REPO_ROOT))
        sample = _REPO_ROOT / "butler" / "gateway" / "__init__.py"
        expected = len(sample.read_text(encoding="utf-8").splitlines())
        tool_out = dispatch_tool("read_file", {"path": str(sample)})
        assert "error" not in tool_out.lower()[:80]
        assert str(expected) in tool_out or "|" in tool_out

        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _tool_response("read_file", {"path": str(sample)}),
            _text_response(f"__init__.py 共有 {expected} 行。"),
        ]
        link_llm_stream_mock(mock_complete, mock_stream)

        out = gateway_handler.handle_message(
            "请帮我查看 butler/gateway/__init__.py 文件有多少行",
            session_key="wechat:u1",
            platform="wechat",
        )

        assert str(expected) in out

    def test_344_wechat_truncation(self, gateway_handler):
        long_text = "行" * 3000
        result = LoopResult(status=LoopStatus.COMPLETED, final_response=long_text)
        out = gateway_handler._format_response(result, platform="wechat")
        assert len(out) <= 2000

    def test_345_media_only_prompt(self, gateway_handler, patch_llm):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response("收到，请用文字说明需求。")
        mock_stream.return_value = mock_complete.return_value

        event = MessageEvent(
            text="",
            message_type=MessageType.PHOTO,
            source=SessionSource(platform="wechat", chat_id="u1", user_id="u1"),
            media_urls=["/tmp/fake.jpg"],
            media_types=["image/jpeg"],
        )

        async def _run():
            return await _butler_message_handler(gateway_handler, event)

        with patch(
            "butler.gateway.minimax_vlm.describe_image",
            return_value="（测试识图摘要）",
        ):
            out = asyncio.run(_run())

        assert out is not None
        assert mock_complete.called
        call_args = mock_complete.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_contents = [
            m.get("content", "")
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        assert any(
            needle in c
            for c in user_contents
            for needle in ("收到媒体消息", "[微信图片]", "图片识别", "测试识图摘要")
        )

    def test_346_health_command(self, gateway_handler):
        out = gateway_handler.handle_message("/health", session_key="wechat:u1", platform="wechat")
        assert "Butler 简要诊断" in out or "Butler 诊断" in out or "暂无诊断" in out


@pytest.mark.integration
class TestManualGuide35Slash:
    """§3.5 微信斜杠命令"""

    @pytest.mark.parametrize(
        "cmd,needle",
        [
            ("/status", "Butler 状态"),
            ("/状态", "Butler 状态"),
            ("/model", "butler"),
            ("/模型", "butler"),
            ("/new", "已清空"),
            ("/新对话", "已清空"),
            ("/detail", "暂无可展示"),
            ("/详细", "暂无可展示"),
        ],
    )
    def test_slash_aliases(self, gateway_handler, cmd, needle):
        out = gateway_handler.handle_message(cmd, session_key="wechat:u1", platform="wechat")
        assert needle in out

    def test_352_projects_list(self, gateway_handler_with_project):
        out = gateway_handler_with_project.handle_message(
            "/projects", session_key="wechat:u1", platform="wechat"
        )
        assert "test-project" in out

    def test_352_projects_list_chinese_alias(self, gateway_handler_with_project):
        out = gateway_handler_with_project.handle_message(
            "/项目", session_key="wechat:u1", platform="wechat"
        )
        assert "test-project" in out

    def test_354_model_switch(self, gateway_handler):
        out = gateway_handler.handle_message(
            "/model butler minimax/MiniMax-M2.5",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "已设置" in out or "已临时设置" in out
        assert "MiniMax-M2.5" in out

    def test_355_switch_project(self, tmp_path, monkeypatch):
        from tests.gateway.test_gateway_handler import _setup_projects

        _setup_projects(tmp_path, monkeypatch)
        handler = ButlerMessageHandler(channel="gateway")
        out = handler.handle_message(
            "/switch test-project",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "已切换到项目" in out

    def test_356b_new_clears_chat_experience_recall(self, gateway_handler, patch_llm):
        from butler.core.agent_loop import LoopStatus
        from butler.session.keys import build_session_key
        from butler.session.lifecycle import inject_turn_memory, sync_turn_memory

        sk = build_session_key(platform="wechat", chat_id="u1", project="")
        sync_turn_memory(
            gateway_handler._orchestrator,
            "请读取 wechat-smoke 文件",
            "已读取并摘要完成。",
            status=LoopStatus.COMPLETED,
            session_id=sk,
        )
        gateway_handler.handle_message("/new", platform="wechat", external_id="u1")

        augmented = inject_turn_memory(
            gateway_handler._orchestrator,
            "我们刚才聊过什么？",
        )
        assert "wechat-smoke" not in augmented

        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response("上一轮对话已清空，无法复述具体细节。")
        mock_stream.return_value = mock_complete.return_value
        out = gateway_handler.handle_message(
            "我们刚才聊过什么？",
            platform="wechat",
            external_id="u1",
        )
        assert "wechat-smoke" not in out

    def test_356_new_clears_memory(self, gateway_handler, patch_llm):
        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _text_response("好的，赵六。"),
            _text_response("我不记得了。"),
        ]
        link_llm_stream_mock(mock_complete, mock_stream)

        sk = "wechat:u1"
        gateway_handler.handle_message("我叫赵六", session_key=sk, platform="wechat")
        gateway_handler.handle_message("/new", session_key=sk, platform="wechat")
        out = gateway_handler.handle_message("我叫什么？", session_key=sk, platform="wechat")

        assert "赵六" not in out or "不记得" in out or "不知道" in out


def _setup_gateway_project(
    tmp_path: Path,
    monkeypatch,
    *,
    with_workflow: bool = False,
    project_folder: str = "test-project",
    project_name: str = "test-project",
    description: str = "Gateway smoke project",
) -> Path:
    """Project workspace under tmp_path; returns project directory."""
    from butler.config import reload_butler_settings
    from tests.gateway.test_gateway_handler import _reset_singletons

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / project_folder
    proj.mkdir()
    (proj / "docs").mkdir()
    (proj / "README.md").write_text(
        "\n".join(f"README line {i}" for i in range(1, 16)),
        encoding="utf-8",
    )
    spec: dict = {
        "name": project_name,
        "type": "software",
        "description": description,
        "workspace": str(proj),
    }
    if with_workflow:
        spec["workflows"] = [{"name": "novel-factory", "description": "demo wf"}]
    import yaml

    (proj / "project.yaml").write_text(
        yaml.safe_dump(spec, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    _reset_singletons()
    reload_butler_settings()
    return proj


@pytest.fixture
def gateway_handler_project(tmp_path, monkeypatch, tmp_butler_home):
    from butler.report import clear_report_cache
    from tests.gateway.test_gateway_handler import _reset_singletons

    clear_report_cache()
    proj = _setup_gateway_project(tmp_path, monkeypatch)
    empty = tmp_path / "empty-hint"
    empty.mkdir()
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    # Sprint 17 SEC-11: 走 dev 旁路跳过 owner 校验 (与 gateway_handler 一致).
    monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
    # R1: allow project workspace under tmp_path; production path-safety
    # default rejects paths outside /home/ailearn/projects.
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    pm = handler._orchestrator.project_manager
    pm.switch_project_for_chat(platform="wechat", chat_id="u1", name="test-project")
    pm.switch_project_for_chat(platform="wechat", chat_id="u2", name="test-project")
    return handler, proj


@pytest.mark.integration
class TestWechatSmokeDelegate:
    """Maps to wechat-daily-smoke steps 4–4c: delegate, compact reply, /detail."""

    def test_delegate_compact_summary_and_detail(self, gateway_handler_project, patch_llm):
        from butler.report import clear_report_cache, get_last_report

        handler, proj = gateway_handler_project
        clear_report_cache()
        doc_rel = "docs/smoke-gw.md"
        doc_path = proj / doc_rel

        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _tool_response(
                "delegate_task",
                {
                    "role": "content_agent",
                    "task": f"在 {doc_rel} 写一行「微信验收」",
                },
            ),
            _tool_response("write_file", {"path": doc_rel, "content": "微信验收\n"}),
            _text_response("已写入 docs/smoke-gw.md"),
            _text_response("内容代理已完成，发 /详细 可看变更。"),
        ]
        link_llm_stream_mock(mock_complete, mock_stream)

        out = handler.handle_message(
            "请交给内容代理：在 docs 写 smoke-gw.md，正文写微信验收",
            session_key="wechat:u1",
            platform="wechat",
        )

        assert doc_path.is_file()
        assert "微信验收" in doc_path.read_text(encoding="utf-8")
        assert len(out) <= 2000
        sk = "wechat:u1:test-project"
        assert "详细" in out or get_last_report(sk) is not None
        report = get_last_report(sk)
        assert report is not None
        assert report.headline

        detail = handler.handle_message("/详细", session_key="wechat:u1", platform="wechat")
        assert "smoke-gw" in detail or "变更" in detail or report.headline in detail

    def test_read_readme_without_delegate(self, gateway_handler_project, patch_llm):
        from butler.execution_context import use_execution_context
        from butler.tools.registry import dispatch_tool

        handler, _proj = gateway_handler_project
        readme_rel = "README.md"
        with use_execution_context(handler._orchestrator, session_key="wechat:u1"):
            tool_out = dispatch_tool("read_file", {"path": readme_rel})
        assert "error" not in tool_out.lower()[:80]

        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _tool_response("read_file", {"path": readme_rel}),
            _text_response("README 共 15 行左右。"),
        ]
        link_llm_stream_mock(mock_complete, mock_stream)

        handler._session_registry.reset_all()
        with patch(
            "butler.tools.registry.dispatch_tool",
            wraps=dispatch_tool,
        ) as spy:
            out = handler.handle_message(
                "请读取当前项目 README 前 15 行，用纯文字摘要，不要委派",
                session_key="wechat:u1",
                platform="wechat",
            )
            tool_names = [c[0][0] for c in spy.call_args_list if c[0]]
        assert "delegate_task" not in tool_names
        assert "read_file" in tool_names
        assert "15" in out or "README" in out


@pytest.mark.integration
class TestWechatSmokeWorkflow:
    """Maps to smoke steps 8–8c (gateway path for /详细 after workflow)."""

    def test_workflow_run_then_detail(self, tmp_path, monkeypatch, tmp_butler_home, patch_llm):
        from butler.report import clear_report_cache
        from butler.task_orchestrator import AgentResult, TaskGraphResult
        from tests.gateway.test_gateway_handler import _reset_singletons

        clear_report_cache()
        _setup_gateway_project(tmp_path, monkeypatch, with_workflow=True)
        # Sprint 17 SEC-11: 走 dev 旁路跳过 owner 校验.
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        _reset_singletons()
        handler = ButlerMessageHandler(channel="gateway")
        handler._orchestrator.project_manager.switch_project_for_chat(
            platform="wechat", chat_id="u1", name="test-project",
        )

        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response("好的")
        mock_stream.return_value = mock_complete.return_value

        listed = handler.handle_message("/工作流 list", session_key="wechat:u1", platform="wechat")
        assert "novel-factory" in listed

        graph = TaskGraphResult(
            success=True,
            nodes={
                "draft": AgentResult(success=True, response="draft ok"),
                "review": AgentResult(success=True, response="review ok"),
            },
            execution_order=["draft", "review"],
        )
        from butler.workflows.loader import resolve_workflow
        from butler.workflows.runner import WorkflowRunner

        project = handler._orchestrator.project_manager.get_current()
        wf = resolve_workflow(project, "novel-factory")
        assert wf is not None

        with patch("butler.workflows.runner.WorkflowRunner.run", return_value=graph):
            run_out = handler.handle_message(
                "/工作流 run novel-factory 写一句验收说明",
                session_key="wechat:u1",
                platform="wechat",
            )
        WorkflowRunner._cache_workflow_report(wf, graph, session_key="wechat:u1:test-project")
        assert "novel-factory" in run_out

        detail = handler.handle_message("/详细", session_key="wechat:u1", platform="wechat")
        assert "novel-factory" in detail or "draft" in detail or "验收" in detail

    def test_workflow_run_via_execute_graph_caches_detail(
        self, tmp_path, monkeypatch, tmp_butler_home, patch_llm
    ):
        from unittest.mock import AsyncMock

        from butler.report import clear_report_cache, get_last_report
        from butler.task_orchestrator import AgentResult, TaskGraphResult
        from butler.workflows.runner import TaskOrchestrator
        from tests.gateway.test_gateway_handler import _reset_singletons

        clear_report_cache()
        _setup_gateway_project(tmp_path, monkeypatch, with_workflow=True)
        monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
        # Sprint 17 SEC-11: 走 dev 旁路跳过 owner 校验.
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        _reset_singletons()
        handler = ButlerMessageHandler(channel="gateway")
        handler._orchestrator.project_manager.switch_project_for_chat(
            platform="wechat", chat_id="u1", name="test-project",
        )

        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response("好的")
        mock_stream.return_value = mock_complete.return_value

        graph = TaskGraphResult(
            success=True,
            nodes={
                "draft": AgentResult(success=True, response="draft via graph"),
                "review": AgentResult(success=True, response="review via graph"),
            },
            execution_order=["draft", "review"],
        )

        with patch.object(
            TaskOrchestrator,
            "execute_graph",
            new_callable=AsyncMock,
            return_value=graph,
        ):
            run_out = handler.handle_message(
                "/工作流 run novel-factory 写一句验收说明",
                session_key="wechat:u1",
                platform="wechat",
            )

        report = get_last_report("wechat:u1:test-project")
        assert report is not None
        assert "novel-factory" in run_out
        assert "draft" in report.summary or "draft via graph" in report.summary

        detail = handler.handle_message("/详细", session_key="wechat:u1", platform="wechat")
        assert "novel-factory" in detail or "draft" in detail


@pytest.mark.integration
class TestWechatSmokeSlashProjects:
    """Maps to smoke steps 0–2: /状态, /切换 display name, /状态 again."""

    def test_switch_lingwen_display_name_then_status(
        self, tmp_path, monkeypatch, tmp_butler_home
    ):
        from tests.gateway.test_gateway_handler import _reset_singletons

        _setup_gateway_project(
            tmp_path,
            monkeypatch,
            project_folder="LingWen",
            project_name="灵文",
            description="小说工厂流水线验收",
        )
        monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
        # Sprint 17 SEC-11: 走 dev 旁路跳过 owner 校验.
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        _reset_singletons()
        handler = ButlerMessageHandler(channel="gateway")

        switched = handler.handle_message(
            "/切换 灵文",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "已切换到项目: 灵文" in switched

        status = handler.handle_message("/状态", session_key="wechat:u1", platform="wechat")
        assert "灵文" in status
        assert "Butler 状态" in status


@pytest.mark.integration
class TestWechatSmokeDevDelegate:
    """Maps to smoke step 5: dev agent read-only check via delegate_task."""

    def test_dev_agent_check_without_write(
        self, gateway_handler_project, patch_llm
    ):
        from butler.tools.registry import dispatch_tool

        handler, proj = gateway_handler_project
        smoke_rel = "docs/wechat-smoke.md"
        (proj / smoke_rel).write_text("微信验收\n", encoding="utf-8")

        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _tool_response(
                "delegate_task",
                {
                    "role": "dev_agent",
                    "task": f"只读检查 {smoke_rel} 是否存在并读前几行",
                },
            ),
            _tool_response("read_file", {"path": smoke_rel}),
            _text_response("开发代理确认：文件存在。"),
            _text_response("已委派开发代理完成检查，文件存在。"),
        ]
        link_llm_stream_mock(mock_complete, mock_stream)

        handler._session_registry.reset_all()
        with patch(
            "butler.tools.registry.dispatch_tool",
            wraps=dispatch_tool,
        ) as spy:
            out = handler.handle_message(
                "请委派开发代理：只检查 docs/wechat-smoke.md 是否存在并读前几行，不要改代码",
                session_key="wechat:u1",
                platform="wechat",
            )
            tool_names = [c[0][0] for c in spy.call_args_list if c[0]]
            delegate_roles = [
                c[0][1].get("role")
                for c in spy.call_args_list
                if c[0] and c[0][0] == "delegate_task"
            ]

        assert "delegate_task" in tool_names
        assert any(r in ("dev_agent", "dev") for r in delegate_roles)
        assert "write_file" not in tool_names
        assert "开发代理" in out or "存在" in out or "检查" in out


@pytest.mark.integration
class TestWechatSmokeProjectMemory:
    """Maps to smoke step 7: project context survives /new; chat secrets do not."""

    def test_after_new_answers_project_purpose(
        self, tmp_path, monkeypatch, tmp_butler_home, patch_llm
    ):
        from butler.core.agent_loop import LoopStatus
        from butler.session.keys import build_session_key
        from butler.session.lifecycle import sync_turn_memory
        from tests.gateway.test_gateway_handler import _reset_singletons

        desc = "小说工厂流水线验收专用描述"
        _setup_gateway_project(
            tmp_path,
            monkeypatch,
            project_folder="LingWen",
            project_name="灵文",
            description=desc,
        )
        monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
        _reset_singletons()
        handler = ButlerMessageHandler(channel="gateway")
        handler.handle_message("/切换 灵文", session_key="wechat:u1", platform="wechat")

        sk = build_session_key(platform="wechat", chat_id="u1", project="灵文")
        sync_turn_memory(
            handler._orchestrator,
            "请读取 wechat-only-secret-42",
            "已读完 secret 文件。",
            status=LoopStatus.COMPLETED,
            session_id=sk,
        )
        handler.handle_message("/新对话", session_key="wechat:u1", platform="wechat")

        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response(
            f"当前项目是灵文，用途：{desc}。"
        )
        mock_stream.return_value = mock_complete.return_value

        out = handler.handle_message(
            "当前是什么项目？灵文项目是做什么的？",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "灵文" in out
        assert "小说工厂" in out or desc in out
        assert "wechat-only-secret-42" not in out

        call_args = mock_complete.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_blob = " ".join(
            str(m.get("content", ""))
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        )
        assert "wechat-only-secret-42" not in user_blob
        assert "灵文" in user_blob or desc in user_blob


@pytest.mark.integration
class TestWechatSmokeDetailAlias:
    """Maps to smoke step 4b: 「详细」without leading slash."""

    def test_plain_detail_after_delegate(self, gateway_handler_project, patch_llm):
        from butler.report import clear_report_cache, get_last_report

        handler, proj = gateway_handler_project
        clear_report_cache()
        doc_rel = "docs/smoke-detail-alias.md"
        (proj / "docs").mkdir(exist_ok=True)

        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _tool_response(
                "delegate_task",
                {"role": "content_agent", "task": f"写 {doc_rel}"},
            ),
            _tool_response("write_file", {"path": doc_rel, "content": "ok\n"}),
            _text_response("已完成。"),
            _text_response("发「详细」可看报告。"),
        ]
        link_llm_stream_mock(mock_complete, mock_stream)

        handler.handle_message(
            "请交给内容代理写 docs/smoke-detail-alias.md",
            session_key="wechat:u1",
            platform="wechat",
        )
        sk = "wechat:u1:test-project"
        assert get_last_report(sk) is not None

        with patch.object(handler, "_get_or_create_loop") as mock_get:
            detail = handler.handle_message(
                "详细",
                session_key="wechat:u1",
                platform="wechat",
            )
        mock_get.assert_not_called()
        assert "smoke-detail-alias" in detail or "变更" in detail


@pytest.mark.integration
class TestWechatSmokeDetailSections:
    """P2: /详细 with section aliases (changes only)."""

    def test_detail_changes_section_via_gateway(self, gateway_handler_project):
        from butler.report import AgentReport, Change, cache_report, clear_report_cache

        handler, _proj = gateway_handler_project
        clear_report_cache()
        cache_report(
            AgentReport(
                headline="内容代理已完成",
                summary="完整摘要含决策与问题",
                changes=[
                    Change(file="docs/a.md", action="created", description="new"),
                    Change(file="docs/b.md", action="modified", description="edit"),
                ],
                decisions=["采用方案 A"],
                issues=["无阻塞问题"],
            ),
            session_key="wechat:u1:test-project",
        )

        changes_only = handler.handle_message(
            "/详细 变更",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "a.md" in changes_only
        assert "b.md" in changes_only
        assert "方案 A" not in changes_only

        alias = handler.handle_message(
            "详细 changes",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "a.md" in alias
        assert "完整摘要" not in alias

    def test_detail_decisions_section_via_gateway(self, gateway_handler_project):
        from butler.report import AgentReport, Change, cache_report, clear_report_cache

        handler, _proj = gateway_handler_project
        clear_report_cache()
        cache_report(
            AgentReport(
                headline="完成",
                changes=[Change(file="docs/x.md", action="created", description="")],
                decisions=["采用方案 A", "暂缓方案 B"],
                issues=["无阻塞"],
            ),
            session_key="wechat:u1:test-project",
        )

        out = handler.handle_message(
            "/详细 决策",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "方案 A" in out
        assert "方案 B" in out
        assert "x.md" not in out

    def test_detail_issues_section_via_gateway(self, gateway_handler_project):
        from butler.report import AgentReport, cache_report, clear_report_cache

        handler, _proj = gateway_handler_project
        clear_report_cache()
        cache_report(
            AgentReport(
                headline="完成",
                decisions=["某决策"],
                issues=["磁盘空间不足", "待确认权限"],
            ),
            session_key="wechat:u1:test-project",
        )

        out = handler.handle_message(
            "详细 问题",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "磁盘空间" in out
        assert "权限" in out
        assert "某决策" not in out
