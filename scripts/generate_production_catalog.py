#!/usr/bin/env python3
"""Generate production_utterance_catalog.yaml — 脱敏真机 + 线束命令（严断言）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

OUT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "corpus"
    / "suites"
    / "wechat_real"
    / "lw_real"
    / "production_utterance_catalog.yaml"
)


def _row(
    pid: str,
    user: str,
    *,
    kind: str = "llm",
    script: str | None = None,
    fixture: str = "lingwen",
    setup: str | None = None,
    expect: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": pid,
        "user": user,
        "category": "production_real",
        "fixture": fixture,
        "kind": kind,
        "tier": "production",
        "quality": "strict",
        "runner": "production",
        "source_file": "production/脱敏真机20260522",
        "expect": expect or {},
    }
    if script:
        row["script"] = script
    if setup:
        row["setup"] = setup
    return row


def _harness_row(
    pid: str,
    user: str,
    *,
    category: str,
    expect: dict[str, Any],
    fixture: str = "lingwen",
) -> dict[str, Any]:
    row = _row(pid, user, kind="command", fixture=fixture, expect=expect)
    row["category"] = category
    row["source_file"] = "production/harness-2026-05"
    return row


def main() -> None:
    rows = [
        _row("PROD-001", "那你在灵文一号项目下面尝试新建一个文件，然后往里面写一点代码", script="delegate_create_hello", expect={"file_exists": ["docs/test_hello.txt"]}),
        _row("PROD-002", "我要看一下详细信息", kind="detail", setup="prior_delegate_create_hello", expect={"no_llm": True, "response_contains_any": ["【本报告任务】", "test_hello"]}),
        _row("PROD-003", "/详细", kind="detail", setup="prior_delegate_create_hello", expect={"no_llm": True, "response_contains": ["test_hello"]}),
        _row("PROD-004", "你帮我创建一个Python文件，然后往里边写一段代码逻辑", script="delegate_create_demo_py", expect={"file_exists": ["docs/demo_logic.py"]}),
        _row("PROD-005", "好，帮我把你刚才创建的两个文件删掉", script="delegate_delete_both", expect={"file_missing": ["docs/test_hello.txt", "docs/demo_logic.py"], "response_contains_any": ["删除", "完成"]}),
        _row("PROD-006", "切换到演示试点", kind="command", fixture="dual", expect={"response_contains": ["演示试点"]}),
        _row("PROD-007", "切换回灵文1号", kind="command", fixture="dual", setup="switch_to_demo", expect={"response_contains": ["灵文1号"]}),
        _row("PROD-008", "当前在哪个项目？", kind="command", fixture="dual", expect={"response_contains_any": ["灵文", "当前项目"]}),
        _row("PROD-009", "/新对话", kind="command", setup="prior_chat_turn", expect={"response_contains_any": ["清空", "新对话"]}),
        _row("PROD-010", "刚才聊了什么", script="deny_prior_details", setup="prior_chat_then_new", expect={"response_contains_any": ["清空", "无法", "复述"]}),
        _row("PROD-011", "帮我总结一下刚才做了什么", script="recap_hello", setup="prior_delegate_create_hello", expect={"response_contains_any": ["刚才", "完成", "创建"]}),
        _row("PROD-012", "用三句话说明结果", script="brief_three_lines", setup="cached_report_hello", expect={"response_max_lines": 6}),
        _row("PROD-013", "看一下README", script="read_readme", expect={"response_contains_any": ["README", "行"], "tools_include": ["read_file"]}),
        _row("PROD-014", "报错了，帮看下原因", script="error_guide", expect={"response_contains_any": ["报错", "诊断"]}),
        _row("PROD-015", "继续刚才的任务", script="continue_delete_hello", setup="prior_delegate_create_hello", expect={"file_missing": ["docs/test_hello.txt"]}),
        _row("PROD-016", "请交给开发代理：删除 docs/missing-prod.txt", script="dev_delete_fail", expect={"uses_delegate": True, "response_contains_any": ["未能", "失败"]}),
        _row("PROD-017", "/详细", kind="detail", setup="cached_report_delete_fail", expect={"no_llm": True, "response_contains_any": ["未能", "【本报告任务】"]}),
        _row("PROD-018", "帮我读一下 /etc/passwd", script="refuse_unsafe", expect={"response_contains_any": ["拒绝", "安全"]}),
        _row("PROD-019", "完整报告", kind="detail", setup="cached_report_delete", expect={"no_llm": True, "response_contains": ["【本报告任务】"]}),
        _row("PROD-020", "委派开发者跑一下单元测试", script="delegate_pytest", expect={"uses_delegate": True}),
        _row("PROD-021", "不要写代码，先给方案", script="plan_only", expect={"no_write_tools": True}),
        _row("PROD-022", "读取 docs 目录有哪些文件", script="list_docs", setup="notes_on_disk", expect={"tools_include": ["list_directory"]}),
        _row("PROD-023", "切换灵文一号", kind="command", fixture="dual", expect={"response_contains_any": ["灵文", "切换"]}),
        _row("PROD-024", "切到灵文1号", kind="command", fixture="dual", expect={"response_contains_any": ["灵文", "切换"]}),
        _row("PROD-025", "看一下novel-factory/workflow_state.json", script="read_workflow_state", fixture="lingwen_workflow", setup="workflow_state_on_disk", expect={"response_contains_any": ["phase", "step"]}),
        _row("PROD-026", "帮我设一个定时任务，每天早8点跑报告", script="schedule_ops_ack", expect={"response_contains_any": ["定时", "任务"]}),
        _row("PROD-027", "/运行 job-20260522-001", kind="command", setup="copy_runtime_jobs", expect={"response_contains_any": ["运行", "任务", "job"]}),
        _row("PROD-028", "[图片] 这个报错什么意思", script="wechat_image_limit", expect={"response_contains_any": ["图片", "文字", "粘贴"]}),
        _row("PROD-029", "你直接改代码啊，干嘛还要委派", script="lead_refuse_direct_write", expect={"no_write_tools": True, "response_contains_any": ["委派", "代理"]}),
        _row("PROD-030", "今天天气怎么样", script="off_topic_redirect", expect={"response_contains_any": ["项目", "助手"]}),
        _harness_row(
            "PROD-031",
            "/计划",
            category="harness_plan",
            expect={
                "no_llm": True,
                "response_contains_any": ["规划模式", "只读"],
            },
        ),
        _harness_row(
            "PROD-032",
            "/任务",
            category="T_debugging",
            expect={
                "no_llm": True,
                "response_contains_any": ["委派任务", "暂无"],
            },
        ),
        _harness_row(
            "PROD-033",
            "/执行",
            category="harness_plan",
            expect={
                "no_llm": True,
                "response_contains_any": ["退出", "规划"],
            },
        ),
        _harness_row(
            "PROD-034",
            "/诊断",
            category="T_debugging",
            expect={"no_llm": True, "response_contains": ["上下文用量"]},
        ),
        _harness_row(
            "PROD-035",
            "/状态",
            category="harness_plan",
            expect={
                "no_llm": True,
                "response_contains": ["规划模式"],
            },
        ),
    ]
    doc = {
        "meta": {"version": "2026-05-24-production-r1", "entry_count": len(rows)},
        "utterance_catalog": rows,
    }
    OUT.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(rows)} production entries → {OUT}")


if __name__ == "__main__":
    main()
