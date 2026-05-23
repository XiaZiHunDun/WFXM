"""Shared mock LLM script profiles for gateway corpus runners."""

from __future__ import annotations

from typing import Any

from tests.test_gateway_acceptance import _text_response, _tool_response
from tests.test_gateway_dev_conversations import (
    HELLO_REL,
    _delegate_create_hello_script,
    _delegate_create_py_script,
    _delegate_delete_both_script,
)

README_REL = "README.md"


def pad_script(script: list[Any]) -> list[Any]:
    tail = _text_response("好的，已记录。")
    return list(script) + [tail] * 8


def final_text_from_script(script: list[Any]) -> str:
    for item in reversed(script):
        content = getattr(item, "content", None)
        if content:
            return str(content)
    return "好的。"


def needs_real_tools(expect: dict[str, Any]) -> bool:
    return bool(
        expect.get("file_exists")
        or expect.get("file_missing")
        or expect.get("uses_delegate")
        or expect.get("tools_include")
        or expect.get("tools_exclude")
        or expect.get("no_write_tools")
    )


def script_profiles() -> dict[str, list[Any]]:
    return {
        "read_readme": [
            _tool_response("read_file", {"path": README_REL}),
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
            _text_response("当前 phase 为 draft，step 为 outline。"),
        ],
        "read_project_yaml": [
            _tool_response("read_file", {"path": "project.yaml"}, tool_id="b02-1"),
            _text_response("project.yaml：灵文1号，software 类型，含 delegate_task 等工具。"),
        ],
        "delegate_create_hello": _delegate_create_hello_script(),
        "delegate_create_demo_py": _delegate_create_py_script(),
        "delegate_delete_both": _delegate_delete_both_script(),
        "schedule_ops_ack": [
            _text_response("已更新定时任务规则，下次执行将按新计划运行。"),
        ],
        "off_topic_redirect": [
            _text_response("我是灵文项目助手，不负责天气/闲聊，有项目任务请直接说。"),
        ],
        "wechat_image_limit": [
            _text_response("暂不支持识别图片，请粘贴报错文字或描述问题。"),
        ],
        "memory_conflict_answer": [
            _text_response("已定位相关记忆，将按您的最新说明更新并进入待审队列。"),
        ],
        "agent_roles_explain": [
            _text_response(
                "content 负责文档与内容，dev 负责代码与文件操作，review 负责审查。"
            ),
        ],
        "export_limit_ack": [
            _text_response("暂不支持打包下载，可逐个读取文件或使用 git clone。"),
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
                {"role": "review", "task": "审查 docs/wechat-smoke.md 结构"},
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
                {"role": "content_agent", "task": "写 docs/pilot-log.md 验收记录"},
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
                {"role": "dev", "task": "运行 pytest tests/test_report.py -q"},
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
        "generic_ack": [
            _text_response("好的，已收到您的需求，我会在灵文1号项目下处理。"),
        ],
        "refuse_unsafe": [
            _text_response("出于安全考虑，无法访问该路径或执行该操作。"),
        ],
        "generic_delegate_write": [
            _tool_response(
                "delegate_task",
                {"role": "dev", "task": "按用户要求写入项目文件"},
                tool_id="ref-w1",
            ),
            _tool_response(
                "write_file",
                {"path": "docs/ref-task.md", "content": "done\n"},
                tool_id="ref-w2",
            ),
            _text_response("已委派开发代理并完成写入。"),
        ],
        "generic_delegate_delete": [
            _tool_response(
                "delegate_task",
                {"role": "dev", "task": "删除用户指定的项目内文件"},
                tool_id="ref-d1",
            ),
            _tool_response("delete_file", {"path": "docs/ref-task.md"}, tool_id="ref-d2"),
            _text_response("开发代理已完成删除。"),
        ],
    }
