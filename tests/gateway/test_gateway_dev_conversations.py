"""WeChat conversation scenarios derived from real LingWen dialogue (2026-05-22).

Catalog: tests/corpus/suites/wechat_real/lw_real/corpus.yaml
Design: docs/plans/wechat-real-dialogue-test-scenarios-2026-05.md

Run (L2 corpus entry — prefer):
  PYTHONPATH=. pytest tests/corpus/runners/test_gateway_golden.py -q

Legacy direct:
  PYTHONPATH=. pytest tests/gateway/test_gateway_dev_conversations.py -q
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from butler.gateway.message_handler import ButlerMessageHandler
from butler.project import Project
from butler.report import AgentReport, Change, cache_report, clear_report_cache, get_last_report
from butler.tools.project_tools import allowed_tool_names_for_project
from tests.gateway.test_gateway_acceptance import (
    LLM_PATCH,
    _text_response,
    _tool_response,
)

pytestmark = [pytest.mark.integration, pytest.mark.corpus, pytest.mark.corpus_mock]

# Paths from 2026-05-22 鹿角象真机对话
HELLO_REL = "docs/test_hello.txt"
DEMO_REL = "docs/demo_logic.py"
HELLO_CONTENT = "莎丽委派 dev 完成\n"
DEMO_CONTENT = (
    'import os\n\n'
    'def main():\n'
    '    here = os.path.dirname(os.path.abspath(__file__))\n'
    '    path = os.path.join(here, "test_hello.txt")\n'
    '    with open(path, encoding="utf-8") as f:\n'
    '        print("莎丽说：" + f.read().strip())\n\n'
    'if __name__ == "__main__":\n'
    '    main()\n'
)


def _setup_lingwen_gateway_project(tmp_path: Path, monkeypatch) -> Path:
    projects_dir = tmp_path / "projects"
    proj = projects_dir / "LingWen1"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "docs").mkdir(exist_ok=True)
    (proj / "README.md").write_text("# 灵文1号\n", encoding="utf-8")
    spec = {
        "name": "灵文1号",
        "type": "software",
        "description": "小说工厂试点",
        "workspace": str(proj),
        "tools": [
            "read_file",
            "write_file",
            "delete_file",
            "patch",
            "search_files",
            "list_directory",
            "delegate_task",
        ],
    }
    (proj / "project.yaml").write_text(
        yaml.safe_dump(spec, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(proj))
    from butler.config import reload_butler_settings
    from tests.gateway.test_gateway_handler import _reset_singletons

    _reset_singletons()
    reload_butler_settings()
    return proj


def _setup_dual_gateway_projects(tmp_path: Path, monkeypatch) -> Path:
    """灵文1号 + 普通试点项目（多项目切换话术）。"""
    from butler.config import reload_butler_settings
    from tests.gateway.test_gateway_handler import _reset_singletons

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    for folder, name, desc in (
        ("LingWen1", "灵文1号", "小说工厂试点"),
        ("DemoPilot", "普通试点项目", "轻量第二试点"),
    ):
        proj = projects_dir / folder
        proj.mkdir(parents=True)
        (proj / "docs").mkdir(exist_ok=True)
        (proj / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        spec = {
            "name": name,
            "type": "software",
            "description": desc,
            "workspace": str(proj),
            "tools": [
                "read_file",
                "write_file",
                "delete_file",
                "patch",
                "search_files",
                "list_directory",
                "delegate_task",
            ],
        }
        (proj / "project.yaml").write_text(
            yaml.safe_dump(spec, allow_unicode=True),
            encoding="utf-8",
        )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    # F-B: dual project: safe_root covers both LingWen1 + DemoPilot workspaces.
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(projects_dir))
    _reset_singletons()
    reload_butler_settings()
    return projects_dir


def _lingwen_session_key(chat_id: str = "u1") -> str:
    return f"wechat:{chat_id}:灵文1号"


def _bind_llm_script(mock_complete, mock_stream, script: list) -> None:
    from tests.conftest import link_llm_stream_mock

    mock_complete.side_effect = list(script)
    link_llm_stream_mock(mock_complete, mock_stream)


def _assert_not_compact_delegate_card(text: str) -> None:
    """Regression: 「详细信息」must not repeat only the WeChat compact card."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) >= 2 and lines[0].endswith("已完成任务") and "修改" in lines[1]:
        if len(lines) <= 3 and "回复「/详细」" in text:
            pytest.fail("got compact delegate card instead of full detail")


def _delegate_create_hello_script() -> list:
    return [
        _tool_response(
            "delegate_task",
            {
                "role": "dev",
                "task": f"在 {HELLO_REL} 新建文件并写入一行测试内容",
            },
            tool_id="lw-c1",
        ),
        _tool_response(
            "write_file",
            {"path": HELLO_REL, "content": HELLO_CONTENT},
            tool_id="lw-c2",
        ),
        _text_response("已创建 test_hello.txt。"),
        _text_response("开发代理已完成，发 /详细 查看。"),
    ]


def _delegate_create_py_script() -> list:
    return [
        _tool_response(
            "delegate_task",
            {
                "role": "dev",
                "task": f"创建 {DEMO_REL} 并写入 Python 逻辑，可读 {HELLO_REL}",
            },
            tool_id="lw-p1",
        ),
        _tool_response(
            "write_file",
            {"path": DEMO_REL, "content": DEMO_CONTENT},
            tool_id="lw-p2",
        ),
        _tool_response(
            "write_file",
            {"path": HELLO_REL, "content": "Hello, World!\n"},
            tool_id="lw-p3",
        ),
        _text_response("已创建 demo_logic.py 并更新 test_hello.txt。"),
        _text_response("开发代理已完成，发 /详细 查看。"),
    ]


def _delegate_delete_both_script() -> list:
    return [
        _tool_response(
            "delegate_task",
            {
                "role": "dev",
                "task": f"用 delete_file 删除 {HELLO_REL} 和 {DEMO_REL}，禁止 terminal",
            },
            tool_id="lw-d1",
        ),
        _tool_response("delete_file", {"path": HELLO_REL}, tool_id="lw-d2"),
        _tool_response("delete_file", {"path": DEMO_REL}, tool_id="lw-d3"),
        _text_response("两个文件已删除。"),
        _text_response("开发代理已完成删除。"),
    ]


@pytest.fixture
def patch_llm(mock_llm_response):
    with (
        patch(f"{LLM_PATCH}.complete") as mock_complete,
        patch(f"{LLM_PATCH}.stream") as mock_stream,
    ):
        default = mock_llm_response()
        mock_complete.return_value = default
        mock_stream.return_value = default
        yield mock_complete, mock_stream


@pytest.fixture
def lingwen_handler(tmp_path, monkeypatch, tmp_butler_home):
    from tests.gateway.test_gateway_handler import _reset_singletons

    clear_report_cache()
    proj = _setup_lingwen_gateway_project(tmp_path, monkeypatch)
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
    # Mock LLM scripts do not simulate dev_verify; disable auto-verify so
    # DEV_VERIFY_GATE does not mark dialogue-flow regressions as failed.
    monkeypatch.setenv("BUTLER_DEV_AUTO_VERIFY", "0")
    # F1: disable delete maturity gate — fresh test fixtures have no edit/
    # dev history, so delete_file would otherwise be blocked by
    # butler/project/maturity.py:136 (DELETE_MATURITY_GATE).
    monkeypatch.setenv("BUTLER_PROJECT_DELETE_MATURITY_GATE", "0")
    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat",
        chat_id="u1",
        name="灵文1号",
    )
    return handler, proj


@pytest.mark.integration
class TestLingwenRealIntro:
    """LW-INTRO — 真机对话前两轮（能力说明 / 自我介绍）。"""

    def test_lw_intro_01_capabilities(self, lingwen_handler, patch_llm):
        handler, _proj = lingwen_handler
        mock_complete, mock_stream = patch_llm
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _text_response(
                    "主公好，莎丽报到。可统筹灵文1号、委派 content/dev/review、"
                    "记忆与 /运行 查看 runtime。"
                ),
            ],
        )
        out = handler.handle_message(
            "看下你都可以干什么",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "委派" in out or "代理" in out
        assert "记忆" in out or "runtime" in out.lower() or "运行" in out

    def test_lw_intro_02_lead_identity(self, lingwen_handler, patch_llm):
        handler, _proj = lingwen_handler
        mock_complete, mock_stream = patch_llm
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _text_response(
                    "我是灵文1号厂长，专责协调；写代码和改文件交给 dev/content，我通过 delegate_task 派活。"
                ),
            ],
        )
        out = handler.handle_message(
            "介绍一下你自己",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "厂长" in out or "统筹" in out or "委派" in out


@pytest.mark.integration
class TestLingwenRealCreateAndDetail:
    """LW-CREATE / LW-DETAIL — 创建与查看详情（真机 T3–T7 衍射）。"""

    def test_lw_create_01_delegate_hello_file(self, lingwen_handler, patch_llm):
        handler, proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        mock_complete, mock_stream = patch_llm
        _bind_llm_script(mock_complete, mock_stream, _delegate_create_hello_script())

        out = handler.handle_message(
            "那你在灵文一号项目下面尝试新建一个文件，然后往里面写一点代码",
            session_key="wechat:u1",
            platform="wechat",
        )

        assert (proj / HELLO_REL).is_file()
        assert HELLO_CONTENT.strip() in (proj / HELLO_REL).read_text(encoding="utf-8")
        report = get_last_report(sk)
        assert report is not None and report.success
        assert "详细" in out

    def test_lw_detail_01_phrase_after_create_not_compact_card(
        self, lingwen_handler, patch_llm
    ):
        """「我要看一下详细信息」→ 完整报告，不复读短卡片（真机 T4 回归）。"""
        handler, proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        mock_complete, mock_stream = patch_llm
        _bind_llm_script(mock_complete, mock_stream, _delegate_create_hello_script())
        short = handler.handle_message(
            "那你在灵文一号项目下面尝试新建一个文件，然后往里面写一点代码",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "已完成" in short

        with patch.object(handler, "_get_or_create_loop") as mock_loop:
            detail = handler.handle_message(
                "我要看一下详细信息",
                session_key="wechat:u1",
                platform="wechat",
            )
            mock_loop.assert_not_called()

        _assert_not_compact_delegate_card(detail)
        assert HELLO_REL.replace("docs/", "") in detail or HELLO_REL in detail
        report = get_last_report(sk)
        assert report is not None

    def test_lw_create_02_delegate_python_and_hello_update(
        self, lingwen_handler, patch_llm
    ):
        handler, proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        (proj / HELLO_REL).write_text(HELLO_CONTENT, encoding="utf-8")

        mock_complete, mock_stream = patch_llm
        _bind_llm_script(mock_complete, mock_stream, _delegate_create_py_script())
        handler.handle_message(
            "你帮我创建一个Python文件，然后往里边写一段代码逻辑",
            session_key="wechat:u1",
            platform="wechat",
        )

        assert (proj / DEMO_REL).is_file()
        assert "def main" in (proj / DEMO_REL).read_text(encoding="utf-8")
        report = get_last_report(sk)
        assert report is not None and report.success
        assert len(report.changes) >= 2

    def test_lw_detail_02_slash_detail_lists_both_files(
        self, lingwen_handler, patch_llm
    ):
        handler, proj = lingwen_handler
        clear_report_cache()
        (proj / HELLO_REL).write_text("Hello, World!\n", encoding="utf-8")

        mock_complete, mock_stream = patch_llm
        _bind_llm_script(mock_complete, mock_stream, _delegate_create_py_script())
        handler.handle_message(
            "你帮我创建一个Python文件，然后往里边写一段代码逻辑",
            session_key="wechat:u1",
            platform="wechat",
        )

        with patch.object(handler, "_get_or_create_loop") as mock_loop:
            detail = handler.handle_message(
                "/详细",
                session_key="wechat:u1",
                platform="wechat",
            )
            mock_loop.assert_not_called()

        assert "demo_logic" in detail
        assert "test_hello" in detail


@pytest.mark.integration
class TestLingwenRealDelete:
    """LW-DELETE — 双文件删除与报告不串台（真机 T8–T9 衍射）。"""

    def test_lw_delete_01_removes_both_files_in_one_delegate(
        self, lingwen_handler, patch_llm
    ):
        handler, proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        (proj / HELLO_REL).write_text(HELLO_CONTENT, encoding="utf-8")
        (proj / DEMO_REL).write_text(DEMO_CONTENT, encoding="utf-8")

        mock_complete, mock_stream = patch_llm
        _bind_llm_script(mock_complete, mock_stream, _delegate_delete_both_script())
        out = handler.handle_message(
            "好，帮我把你刚才创建的两个文件删掉",
            session_key="wechat:u1",
            platform="wechat",
        )

        assert not (proj / HELLO_REL).exists()
        assert not (proj / DEMO_REL).exists()
        report = get_last_report(sk)
        assert report is not None and report.success
        deleted = [c for c in report.changes if c.action == "deleted"]
        assert len(deleted) >= 2
        assert "详细" in out

    def test_lw_detail_03_after_delete_not_stale_create_report(
        self, lingwen_handler, patch_llm
    ):
        """删除后 /详细 不得仍展示「文件已创建」类创建轮次正文（真机 T9 回归）。"""
        handler, proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        (proj / HELLO_REL).write_text(HELLO_CONTENT, encoding="utf-8")
        (proj / DEMO_REL).write_text(DEMO_CONTENT, encoding="utf-8")

        mock_complete, mock_stream = patch_llm
        _bind_llm_script(mock_complete, mock_stream, _delegate_create_py_script())
        handler.handle_message(
            "你帮我创建一个Python文件，然后往里边写一段代码逻辑",
            session_key="wechat:u1",
            platform="wechat",
        )
        create_report = get_last_report(sk)
        assert create_report is not None
        create_report.summary = (
            "主公，文件已创建完成：demo_logic.py 与 test_hello.txt 配套测试文件。"
        )
        create_report.iterations = 5
        create_report.tool_calls = 4
        cache_report(create_report, session_key=sk)

        _bind_llm_script(mock_complete, mock_stream, _delegate_delete_both_script())
        handler.handle_message(
            "好，帮我把你刚才创建的两个文件删掉",
            session_key="wechat:u1",
            platform="wechat",
        )

        detail = handler.handle_message(
            "/详细",
            session_key="wechat:u1",
            platform="wechat",
        )
        report = get_last_report(sk)
        assert report is not None
        assert "删除" in (report.task_preview or "")
        assert "【本报告任务】" in detail
        assert "文件已创建完成" not in detail
        assert not (proj / HELLO_REL).exists()

    def test_lw_delete_fail_files_remain_and_headline_failed(
        self, lingwen_handler, patch_llm
    ):
        handler, proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        (proj / HELLO_REL).write_text("x\n", encoding="utf-8")
        (proj / DEMO_REL).write_text("y\n", encoding="utf-8")

        mock_complete, mock_stream = patch_llm
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _tool_response(
                    "delegate_task",
                    {"role": "dev", "task": f"删除 {HELLO_REL} 和 {DEMO_REL}"},
                    tool_id="f1",
                ),
                _tool_response("delete_file", {"path": "docs/no-such-a.txt"}, tool_id="f2"),
                _text_response("删除失败。"),
                _text_response("开发代理未能完成删除。"),
            ],
        )
        out = handler.handle_message(
            "好，帮我把你刚才创建的两个文件删掉",
            session_key="wechat:u1",
            platform="wechat",
        )

        assert (proj / HELLO_REL).is_file()
        assert (proj / DEMO_REL).is_file()
        report = get_last_report(sk)
        assert report is not None and not report.success
        assert "未能完成任务" in report.headline
        assert report.issues
        assert "未能完成" in out or "⚠" in out

    def test_lw_delete_fail_detail_shows_issues_not_terminal_menu(
        self, lingwen_handler
    ):
        """失败报告 /详细 应展示 issues，而非旧版「请选择 1/2 开通 terminal」菜单正文。"""
        handler, _proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        cache_report(
            AgentReport(
                headline="开发代理未能完成任务",
                task_preview=f"删除 {HELLO_REL} 和 {DEMO_REL}",
                summary="删除未完成。",
                success=False,
                issues=["Terminal 工具未启用", "请使用 delete_file"],
                iterations=2,
                tool_calls=1,
            ),
            session_key=sk,
        )
        detail = handler.handle_message(
            "/详细",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "未能完成" in detail or "删除未完成" in detail
        assert "请选择" not in detail or "delete_file" in detail


@pytest.mark.integration
class TestLingwenRealGoldenPath:
    """LW-REAL-GOLDEN — 整条真机对话链一次跑通（衍射集成）。"""

    def test_lw_real_golden_path_full_dialogue(self, lingwen_handler, patch_llm):
        handler, proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        mock_complete, mock_stream = patch_llm

        # T3 创建 txt
        _bind_llm_script(mock_complete, mock_stream, _delegate_create_hello_script())
        handler.handle_message(
            "那你在灵文一号项目下面尝试新建一个文件，然后往里面写一点代码",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert (proj / HELLO_REL).is_file()

        # T4 详细信息
        with patch.object(handler, "_get_or_create_loop") as mock_loop:
            d4 = handler.handle_message(
                "我要看一下详细信息",
                session_key="wechat:u1",
                platform="wechat",
            )
            mock_loop.assert_not_called()
        _assert_not_compact_delegate_card(d4)

        # T5 /详细
        d5 = handler.handle_message("/详细", session_key="wechat:u1", platform="wechat")
        assert "test_hello" in d5

        # T6–T7 创建 py
        _bind_llm_script(mock_complete, mock_stream, _delegate_create_py_script())
        handler.handle_message(
            "你帮我创建一个Python文件，然后往里边写一段代码逻辑",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert (proj / DEMO_REL).is_file()

        d7 = handler.handle_message("/详细", session_key="wechat:u1", platform="wechat")
        assert "demo_logic" in d7

        # T8–T9 删除双文件
        _bind_llm_script(mock_complete, mock_stream, _delegate_delete_both_script())
        out8 = handler.handle_message(
            "好，帮我把你刚才创建的两个文件删掉",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert not (proj / HELLO_REL).exists()
        assert not (proj / DEMO_REL).exists()
        assert "已完成" in out8 or "删除" in out8

        d9 = handler.handle_message("/详细", session_key="wechat:u1", platform="wechat")
        report = get_last_report(sk)
        assert report is not None and report.success
        assert "删除" in (report.task_preview or "")
        assert "文件已创建完成" not in d9


@pytest.mark.integration
class TestDevDailyScenarios:
    """Legacy DEV-* scenarios (still valid regressions)."""

    def test_b02_delegate_delete_success_and_detail_task_preview(
        self, lingwen_handler, patch_llm
    ):
        handler, proj = lingwen_handler
        clear_report_cache()
        rel = "docs/wechat-scenario-smoke.txt"
        target = proj / rel
        target.write_text("temp\n", encoding="utf-8")
        sk = _lingwen_session_key()

        mock_complete, mock_stream = patch_llm
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _tool_response(
                    "delegate_task",
                    {"role": "dev", "task": f"删除 {rel}"},
                    tool_id="c1",
                ),
                _tool_response("delete_file", {"path": rel}, tool_id="c2"),
                _text_response("已删除。"),
                _text_response("开发代理已完成删除，发 /详细 查看。"),
            ],
        )

        out = handler.handle_message(
            f"请交给开发代理：删除 {rel}",
            session_key="wechat:u1",
            platform="wechat",
        )

        assert not target.is_file()
        report = get_last_report(sk)
        assert report is not None
        assert report.success is True
        assert "已完成" in report.headline
        assert any(c.action == "deleted" for c in report.changes)
        assert report.task_preview
        assert "详细" in out

        detail = handler.handle_message("详细信息", session_key="wechat:u1", platform="wechat")
        assert "【本报告任务】" in detail
        assert rel in detail

    def test_b03_delegate_delete_failure_wechat_and_report(
        self, lingwen_handler, patch_llm
    ):
        handler, _proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        missing = "docs/missing-scenario.txt"

        mock_complete, mock_stream = patch_llm
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _tool_response(
                    "delegate_task",
                    {"role": "dev", "task": f"删除 {missing}"},
                    tool_id="c1",
                ),
                _tool_response("delete_file", {"path": missing}, tool_id="c2"),
                _text_response("无法删除，文件不存在。"),
                _text_response("开发代理未能删除该文件。"),
            ],
        )

        out = handler.handle_message(
            f"请交给开发代理：删除 {missing}",
            session_key="wechat:u1",
            platform="wechat",
        )

        report = get_last_report(sk)
        assert report is not None
        assert report.success is False
        assert "未能完成任务" in report.headline
        assert report.issues
        assert "未能完成" in out or "⚠" in out

    def test_c02_detail_aliases_skip_llm(self, lingwen_handler):
        handler, _proj = lingwen_handler
        clear_report_cache()
        sk = _lingwen_session_key()
        cache_report(
            AgentReport(
                headline="开发代理已完成任务",
                task_preview="删除 docs/x.txt",
                summary="已删除 docs/x.txt",
                changes=[Change("docs/x.txt", "deleted", "")],
                success=True,
            ),
            session_key=sk,
        )

        with patch.object(handler, "_get_or_create_loop") as mock_loop:
            for phrase in ("详细信息", "我要看一下详细信息", "看一下详细"):
                detail = handler.handle_message(
                    phrase,
                    session_key="wechat:u1",
                    platform="wechat",
                )
                assert "【本报告任务】" in detail
                assert "docs/x.txt" in detail
            mock_loop.assert_not_called()

    def test_c05_sequential_delegate_detail_shows_latest_task(
        self, lingwen_handler, patch_llm
    ):
        handler, proj = lingwen_handler
        clear_report_cache()
        rel = "docs/wechat-scenario-a.txt"
        (proj / rel).write_text("a\n", encoding="utf-8")
        sk = _lingwen_session_key()

        mock_complete, mock_stream = patch_llm
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _tool_response(
                    "delegate_task",
                    {"role": "content_agent", "task": f"写 {rel}"},
                    tool_id="w1",
                ),
                _tool_response("write_file", {"path": rel, "content": "a\n"}, tool_id="w2"),
                _text_response("已写入。"),
                _text_response("内容代理已完成。"),
            ],
        )
        handler.handle_message(
            f"交给内容代理写 {rel}",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert (proj / rel).is_file()

        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _tool_response(
                    "delegate_task",
                    {"role": "dev", "task": f"删除 {rel}"},
                    tool_id="d1",
                ),
                _tool_response("delete_file", {"path": rel}, tool_id="d2"),
                _text_response("已删除。"),
                _text_response("开发代理已完成删除。"),
            ],
        )
        handler.handle_message(
            f"交给开发代理删除 {rel}",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert not (proj / rel).is_file()

        detail = handler.handle_message("/详细", session_key="wechat:u1", platform="wechat")
        report = get_last_report(sk)
        assert report is not None
        assert "删除" in (report.task_preview or "")
        assert "【本报告任务】" in detail
        assert "删除" in detail


@pytest.mark.module_test
class TestDevLeadToolBoundary:
    def test_lingwen_lead_allowlist_matches_daily_expectation(self, tmp_path):
        proj_dir = tmp_path / "lw"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "灵文1号",
                    "workspace": str(proj_dir),
                    "tools": [
                        "read_file",
                        "write_file",
                        "delete_file",
                        "patch",
                        "terminal",
                        "delegate_task",
                    ],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        allowed = allowed_tool_names_for_project(proj, role="lead")
        assert allowed is not None
        assert "delegate_task" in allowed
        assert "read_file" in allowed
        assert "write_file" not in allowed
        assert "patch" not in allowed
        assert "terminal" not in allowed
        assert "delete_file" not in allowed
