"""Data-driven gateway tests from utterance_catalog.yaml.

Run:
  PYTHONPATH=. pytest tests/corpus/runners/test_gateway_utterance_catalog.py -q
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.gateway.message_handler import ButlerMessageHandler
from butler.report import AgentReport, Change, cache_report, clear_report_cache, get_last_report
from tests.corpus.harness.gateway_catalog import (
    apply_catalog_setup,
    assert_expectations,
    catalog_by_id,
    parametrized_catalog_ids,
)
from tests.test_gateway_acceptance import LLM_PATCH, _text_response, _tool_response
from tests.test_gateway_dev_conversations import (
    DEMO_CONTENT,
    DEMO_REL,
    HELLO_CONTENT,
    HELLO_REL,
    _bind_llm_script,
    _delegate_create_hello_script,
    _lingwen_session_key,
    _setup_dual_gateway_projects,
    _setup_lingwen_gateway_project,
)
_README_REL = "README.md"


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


def _pad_script(script: list) -> list:
    tail = _text_response("好的，已记录。")
    return list(script) + [tail] * 8


def _final_text_from_script(script: list) -> str:
    for item in reversed(script):
        content = getattr(item, "content", None)
        if content:
            return str(content)
    return "好的。"


def _needs_real_tools(expect: dict) -> bool:
    return bool(
        expect.get("file_exists")
        or expect.get("file_missing")
        or expect.get("uses_delegate")
        or expect.get("tools_include")
        or expect.get("tools_exclude")
        or expect.get("no_write_tools")
    )


def _script_profiles() -> dict[str, list]:
  return {
      "read_readme": [
          _tool_response("read_file", {"path": _README_REL}),
          _text_response("README 共 15 行左右，项目是小说工厂试点。"),
      ],
      "content_write_smoke": [
          _tool_response(
              "delegate_task",
              {
                  "role": "content_agent",
                  "task": "在 docs/wechat-smoke.md 写微信验收",
              },
              tool_id="smk4-1",
          ),
          _tool_response(
              "write_file",
              {"path": "docs/wechat-smoke.md", "content": "微信验收\n"},
              tool_id="smk4-2",
          ),
          _text_response("已写入 docs/wechat-smoke.md。"),
          _text_response("内容代理已完成，发 /详细 查看。"),
      ],
      "dev_readonly_smoke": [
          _tool_response(
              "delegate_task",
              {
                  "role": "dev",
                  "task": "只读检查 docs/wechat-smoke.md 是否存在并读前几行",
              },
              tool_id="smk5-1",
          ),
          _tool_response("read_file", {"path": "docs/wechat-smoke.md"}, tool_id="smk5-2"),
          _text_response("开发代理确认：文件存在。"),
          _text_response("已委派开发代理完成检查。"),
      ],
      "deny_prior_details": [
          _text_response("上一轮对话已清空，无法复述具体细节。"),
      ],
      "project_memory_answer": [
          _text_response(
              "当前项目是灵文1号，用于小说工厂试点，与正式灵文项目隔离。"
          ),
      ],
      "read_workflow_state": [
          _tool_response(
              "read_file",
              {"path": "novel-factory/workflow_state.json"},
              tool_id="a04-1",
          ),
          _text_response('当前 phase 为 draft，step 为 outline。'),
      ],
      "delegate_patch": [
          _tool_response(
              "delegate_task",
              {
                  "role": "dev",
                  "task": "把 docs/patch-target.txt 的 OLD 改成 NEW",
              },
              tool_id="b04-1",
          ),
          _tool_response(
              "write_file",
              {"path": "docs/patch-target.txt", "content": "NEW\n"},
              tool_id="b04-2",
          ),
          _text_response("已将 OLD 替换为 NEW。"),
          _text_response("开发代理已完成修改。"),
      ],
      "lead_refuse_direct_write": [
          _text_response(
              "我是厂长，不直接 write_file；请说明需求，我用 delegate_task 委派开发代理。"
          ),
      ],
      "delegate_delete_not_terminal": [
          _tool_response(
              "delegate_task",
              {
                  "role": "dev",
                  "task": "用 delete_file 删除 docs/wechat-smoke.md，不要用 terminal",
              },
              tool_id="b06-1",
          ),
          _tool_response("delete_file", {"path": "docs/wechat-smoke.md"}, tool_id="b06-2"),
          _text_response("已委派开发代理用 delete_file 删除。"),
      ],
      "delegate_review": [
          _tool_response(
              "delegate_task",
              {
                  "role": "review",
                  "task": "审查 docs/wechat-smoke.md 结构",
              },
              tool_id="d02-1",
          ),
          _text_response("审核代理：结构清晰，标题与正文分离合理。"),
          _text_response("已委派审核代理完成审查。"),
      ],
      "read_traversal_fail": [
          _text_response("路径不允许访问 workspace 外，请提供项目内相对路径。"),
      ],
      "read_novel_readme": [
          _tool_response(
              "read_file",
              {"path": "novel-factory/README.md"},
              tool_id="r1-1",
          ),
          _text_response("novel-factory 流水线说明摘要…"),
      ],
      "content_write_pilot_log": [
          _tool_response(
              "delegate_task",
              {
                  "role": "content_agent",
                  "task": "写 docs/pilot-log.md 验收记录",
              },
              tool_id="r4-1",
          ),
          _tool_response(
              "write_file",
              {
                  "path": "docs/pilot-log.md",
                  "content": "2026-05-22 微信验收通过\n",
              },
              tool_id="r4-2",
          ),
          _text_response("已写入 pilot-log.md。"),
          _text_response("内容代理已完成。"),
      ],
      "recap_hello": [
          _text_response(
              f"刚才委派开发代理创建了 {HELLO_REL}，写入测试内容，任务已成功完成。"
          ),
      ],
      "brief_three_lines": [
          _text_response(
              "1. 已创建 test_hello.txt。\n2. 写入一行测试内容。\n3. 如需细节请发 /详细。"
          ),
      ],
      "delegate_pytest": [
          _tool_response(
              "delegate_task",
              {
                  "role": "dev",
                  "task": "运行 pytest tests/test_report.py -q",
              },
              tool_id="c6-1",
          ),
          _text_response("pytest 已通过。"),
          _text_response("开发代理已完成单元测试检查。"),
      ],
      "plan_only": [
          _text_response(
              "方案：1) 先列 docs；2) 确认需求后再委派；3) 改完跑 pytest。"
          ),
      ],
      "list_docs": [
          _tool_response("list_directory", {"path": "docs"}, tool_id="c8-1"),
          _text_response("docs 下有 README、notes.md 等。"),
      ],
      "error_guide": [
          _text_response("请贴完整报错栈；也可发 /诊断 查看运维快照。"),
      ],
      "continue_delete_hello": [
          _tool_response(
              "delegate_task",
              {"role": "dev", "task": f"删除 {HELLO_REL}"},
              tool_id="c10-1",
          ),
          _tool_response("delete_file", {"path": HELLO_REL}, tool_id="c10-2"),
          _text_response("test_hello.txt 已删除。"),
          _text_response("开发代理已继续并完成删除任务。"),
      ],
      "dev_delete_one": [
          _tool_response(
              "delegate_task",
              {"role": "dev", "task": "删除 docs/scenario-temp.txt"},
              tool_id="cd1",
          ),
          _tool_response("delete_file", {"path": "docs/scenario-temp.txt"}, tool_id="cd2"),
          _text_response("已删除。"),
          _text_response("开发代理已完成删除。"),
      ],
      "dev_delete_fail": [
          _tool_response(
              "delegate_task",
              {"role": "dev", "task": "删除 docs/missing-utterance.txt"},
              tool_id="cf1",
          ),
          _tool_response(
              "delete_file",
              {"path": "docs/missing-utterance.txt"},
              tool_id="cf2",
          ),
          _text_response("文件不存在，删除失败。"),
          _text_response("开发代理未能完成删除。"),
      ],
      "greeting": [_text_response("主公好，莎丽报到。")],
      "capabilities": [
          _text_response(
              "可统筹灵文1号项目、委派 dev/content 代理、记忆与 /运行 定时任务。"
          ),
      ],
  }


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
def catalog_handlers(tmp_path, monkeypatch, tmp_butler_home):
    import yaml as _yaml
    from tests.test_gateway_handler import _reset_singletons

    clear_report_cache()
    _setup_dual_gateway_projects(tmp_path, monkeypatch)
    lw_proj = _setup_lingwen_gateway_project(tmp_path, monkeypatch)
    spec_path = lw_proj / "project.yaml"
    spec = _yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    spec["workflows"] = [{"name": "novel-factory", "description": "demo wf"}]
    spec_path.write_text(
        _yaml.safe_dump(spec, allow_unicode=True),
        encoding="utf-8",
    )
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

    lingwen_wf = ButlerMessageHandler(channel="gateway")
    lingwen_wf._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat", chat_id="u1", name="灵文1号",
    )

    helpers = {
        "HELLO_REL": HELLO_REL,
        "HELLO_CONTENT": HELLO_CONTENT,
        "delegate_create_hello_script": _delegate_create_hello_script,
        "bind_script": None,
    }

    return {
        "dual": (dual, lw_proj),
        "lingwen": (lingwen, lw_proj),
        "lingwen_workflow": (lingwen_wf, lw_proj),
        "helpers": helpers,
    }


def _extended_setup(
    entry: dict,
    *,
    handler: ButlerMessageHandler,
    proj: Path,
    helpers: dict,
    patch_llm,
) -> str:
    setup = entry.get("setup")
    sk = _resolved_session_key(handler, entry)
    mock_complete, mock_stream = patch_llm

    if setup == "prior_chat_turn":
        _bind_llm_script(mock_complete, mock_stream, [_text_response("好的，已读取 README。")])
        handler.handle_message("请先读 README", session_key=sk, platform="wechat")
        return sk

    if setup == "cached_report_smoke_write":
        clear_report_cache(sk)
        cache_report(
            AgentReport(
                headline="内容代理已完成任务",
                task_preview="写 docs/wechat-smoke.md",
                summary="已写入 wechat-smoke.md",
                changes=[
                    Change("docs/wechat-smoke.md", "created", "微信验收"),
                ],
                success=True,
            ),
            session_key=sk,
        )
        return sk

    if setup == "prior_chat_then_new":
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [_text_response("已读完 wechat-smoke 文件。")],
        )
        handler.handle_message(
            "请读取 wechat-smoke",
            session_key=sk,
            platform="wechat",
        )
        handler.handle_message("/新对话", session_key=sk, platform="wechat")
        return sk

    if setup == "cached_report_multi_changes":
        clear_report_cache(sk)
        cache_report(
            AgentReport(
                headline="开发代理已完成任务",
                summary="完整摘要",
                changes=[
                    Change("docs/a.md", "created", ""),
                    Change("docs/b.md", "modified", ""),
                ],
                success=True,
            ),
            session_key=sk,
        )
        return sk

    if setup == "patch_target_file":
        rel = "docs/patch-target.txt"
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text("OLD\n", encoding="utf-8")
        return sk

    if setup == "scenario_temp_file":
        rel = "docs/scenario-temp.txt"
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text("temp\n", encoding="utf-8")
        return sk

    if setup == "u1_report_u2_empty":
        clear_report_cache()
        u1_sk = handler.resolve_session_key(
            session_key="wechat:u1",
            platform="wechat",
            external_id="u1",
        )
        cache_report(
            AgentReport(headline="report-for-u1-only", summary="u1"),
            session_key=u1_sk,
        )
        return sk

    if setup == "notes_on_disk":
        (proj / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")

    if setup == "copy_runtime_jobs":
        import shutil

        src = Path(__file__).resolve().parents[3] / "projects" / "DemoPilot" / "runtime" / "jobs.yaml"
        if src.is_file():
            dest = proj / "runtime"
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest / "jobs.yaml")

    apply_catalog_setup(
        entry,
        handler=handler,
        proj=proj,
        session_key=sk,
        helpers={
            **helpers,
            "bind_script": lambda script: _bind_llm_script(
                mock_complete, mock_stream, _pad_script(script)
            ),
        },
    )
    return sk


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
        elif kind == "llm":
            script_name = entry.get("script")
            script = _script_profiles().get(script_name or "")
            assert script, f"{catalog_id}: unknown script {script_name!r}"
            expect = entry.get("expect") or {}

            if _needs_real_tools(expect):
                _bind_llm_script(mock_complete, mock_stream, _pad_script(script))
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
                        final_response=_final_text_from_script(script),
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
        assert len(rows) >= 45, f"expected >=45 executable catalog entries, got {len(rows)}"
