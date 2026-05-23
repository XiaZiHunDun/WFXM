#!/usr/bin/env python3
"""Build strict-tier gateway catalog from reference/用户语料/2.md YAML blocks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REF_2 = ROOT / "reference" / "用户语料" / "2.md"
OUT = (
    ROOT
    / "tests"
    / "corpus"
    / "suites"
    / "wechat_real"
    / "lw_real"
    / "reference_utterance_strict.yaml"
)
MULTITURN_OUT = (
    ROOT
    / "tests"
    / "corpus"
    / "suites"
    / "wechat_real"
    / "lw_real"
    / "utterance_multiturn_catalog.yaml"
)


def _parse_yaml_blocks(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in re.findall(r"```yaml\s*(.*?)```", text, flags=re.S | re.I):
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("user") and item.get("id"):
                    rows.append(item)
    return rows


def _fixture(item: dict[str, Any]) -> str:
    proj = str(item.get("project") or "")
    user = str(item.get("user") or "")
    cat = str(item.get("category") or "")
    if "演示" in proj or "演示" in user:
        return "dual"
    if "novel-factory" in user or "workflow" in user.lower():
        return "lingwen_workflow"
    if cat.startswith("L_"):
        return "dual"
    return "lingwen"


def _profile(item: dict[str, Any]) -> dict[str, Any]:
    """Map 2.md REAL-* row → executable catalog entry with strict expect."""
    cat = str(item.get("category") or "")
    user = str(item["user"]).strip()
    u = user.lower()
    ref_id = str(item["id"]).replace("REAL-", "REF-STRICT-")
    entry: dict[str, Any] = {
        "id": ref_id,
        "user": user,
        "category": cat,
        "fixture": _fixture(item),
        "tier": "reference",
        "quality": "strict",
        "source_file": "reference/用户语料/2.md",
        "source_id": item.get("id"),
    }
    variants = [str(v).strip() for v in (item.get("variants") or []) if v]
    if variants:
        entry["variants"] = variants[:6]

    # ── A project session ──
    if cat.startswith("A_"):
        if u in ("/状态", "状态", "/status") or "状态" in u and len(u) < 12:
            entry.update(kind="command", expect={"response_contains_any": ["Butler", "当前项目", "项目"]})
        elif "/新对话" in u or "新会话" in u or ("清" in u and "上下文" in u):
            entry.update(
                kind="command",
                setup="prior_chat_turn",
                expect={"no_llm": True, "response_contains_any": ["清空", "新对话", "上下文"]},
            )
        elif "刚才" in u or "之前" in u or "上一轮" in u:
            entry.update(
                kind="llm",
                script="deny_prior_details",
                setup="prior_chat_then_new",
                expect={
                    "response_excludes": ["wechat-smoke"],
                    "response_contains_any": ["清空", "无法", "复述", "新对话"],
                },
            )
        elif "切换" in u or u.startswith("/切换"):
            entry.update(
                kind="command",
                expect={"response_contains_any": ["切换", "灵文", "演示"]},
            )
        elif any(p in u for p in ("哪些项目", "项目列表", "workspace", "几个项目")):
            entry.update(
                kind="command",
                expect={"response_contains_any": ["项目", "灵文", "演示", "/项目"]},
            )
        else:
            entry.update(
                kind="command",
                expect={"response_contains_any": ["项目", "灵文", "演示", "Butler"]},
            )
        return entry

    # ── B readonly ──
    if cat.startswith("B_"):
        if "workflow_state" in u:
            entry.update(
                kind="llm",
                script="read_workflow_state",
                setup="workflow_state_on_disk",
                expect={"response_contains_any": ["phase", "step", "workflow", "draft", "outline"]},
            )
        elif "project.yaml" in u or "project yaml" in u:
            entry.update(
                kind="llm",
                script="read_project_yaml",
                expect={
                    "tools_include": ["read_file"],
                    "tools_exclude": ["delegate_task"],
                    "response_contains_any": ["project", "yaml", "配置", "灵文"],
                },
            )
        elif "docs" in u and ("哪些" in u or "列表" in u or "有啥" in u):
            entry.update(
                kind="llm",
                script="list_docs",
                setup="notes_on_disk",
                expect={"tools_include": ["list_directory"]},
            )
        elif "readme" in u:
            entry.update(
                kind="llm",
                script="read_readme",
                expect={
                    "tools_include": ["read_file"],
                    "tools_exclude": ["delegate_task"],
                    "response_contains_any": ["README", "行", "灵文"],
                },
            )
        else:
            entry.update(
                kind="llm",
                script="plan_only",
                expect={"no_write_tools": True, "response_contains_any": ["方案", "确认", "先"]},
            )
        return entry

    # ── C delegate ──
    if cat.startswith("C_"):
        if "failure" in cat or "失败" in u:
            entry.update(
                kind="llm",
                script="dev_delete_fail",
                expect={
                    "uses_delegate": True,
                    "response_contains_any": ["未能", "失败", "不存在", "⚠"],
                },
            )
        elif "delete" in cat or "删" in u:
            entry.update(
                kind="llm",
                script="dev_delete_one",
                setup="scenario_temp_file",
                expect={"uses_delegate": True, "file_missing": ["docs/scenario-temp.txt"]},
            )
        elif "continue" in cat or "继续" in u:
            entry.update(
                kind="llm",
                script="continue_delete_hello",
                setup="prior_delegate_create_hello",
                expect={
                    "file_missing": ["docs/test_hello.txt"],
                    "response_contains_any": ["删除", "已完成"],
                },
            )
        elif "review" in cat or "审查" in u or "review" in u:
            entry.update(
                kind="llm",
                script="delegate_review",
                setup="smoke_md_on_disk",
                expect={"uses_delegate": True, "response_contains_any": ["审核", "代理"]},
            )
        elif "test" in cat or "pytest" in u or "单元测试" in u:
            entry.update(kind="llm", script="delegate_pytest", expect={"uses_delegate": True})
        elif "boundary" in cat or "直接写" in u:
            entry.update(
                kind="llm",
                script="lead_refuse_direct_write",
                expect={"no_write_tools": True, "response_contains_any": ["委派", "delegate"]},
            )
        elif "check" in cat or "检查" in u or "是否存在" in u:
            entry.update(
                kind="llm",
                script="dev_readonly_smoke",
                setup="smoke_md_on_disk",
                expect={"uses_delegate": True, "response_contains_any": ["存在", "检查", "代理"]},
            )
        elif "content" in cat or "内容代理" in u:
            entry.update(
                kind="llm",
                script="content_write_smoke",
                expect={"uses_delegate": True, "file_exists": ["docs/wechat-smoke.md"]},
            )
        else:
            entry.update(
                kind="llm",
                script="generic_delegate_write",
                expect={"uses_delegate": True, "response_contains_any": ["代理", "委派", "完成"]},
            )
        return entry

    # ── D detail ──
    if cat.startswith("D_"):
        if ("详细" not in u and "/详细" not in u) and "报告" in u:
            entry.update(
                kind="llm",
                script="recap_hello",
                setup="cached_report_delete",
                expect={"response_contains_any": ["报告", "删除", "代理", "完成"]},
            )
            return entry
        entry.update(
            kind="detail",
            setup="cached_report_delete",
            expect={"no_llm": True, "response_contains_any": ["【本报告任务】", "变更", "删除", "详细"]},
        )
        return entry

    # ── E memory ──
    if cat.startswith("E_"):
        if u.startswith("/开发") or u.startswith("/dev-"):
            entry.update(
                kind="command",
                expect={"response_contains_any": ["开发", "状态", "代理", "Butler"]},
            )
            return entry
        if "/记忆" in u or "待审" in u or "pending" in u:
            entry.update(
                kind="command",
                expect={"response_contains_any": ["记忆", "待审", "Pending", "没有"]},
            )
        elif "图谱" in u or "三元组" in u:
            entry.update(kind="command", expect={"response_contains_any": ["记忆", "图谱", "三元组"]})
        else:
            entry.update(
                kind="llm",
                script="project_memory_answer",
                expect={"response_contains_any": ["记忆", "项目", "灵文"]},
            )
        return entry

    # ── F workflow ──
    if cat.startswith("F_"):
        if u.startswith("/运行") or u.startswith("/run"):
            entry.update(
                kind="command",
                expect={"response_contains_any": ["运行", "任务", "job", "定时", "不存在", "Butler"]},
            )
        elif "/工作流" in u or "工作流" in u:
            entry.update(kind="command", expect={"response_contains_any": ["工作流", "novel-factory"]})
        elif "/定时" in u:
            entry.update(kind="command", expect={"response_contains_any": ["定时", "任务", "runtime"]})
        elif "定时" in u or "早8点" in u or "每天" in u:
            entry.update(
                kind="llm",
                script="generic_ack",
                expect={"response_contains_any": ["定时", "任务", "报告", "好的"]},
            )
        else:
            entry.update(kind="command", expect={"response_contains_any": ["工作流", "定时", "运行"]})
        return entry

    # ── G safety / error ──
    if cat.startswith("G_"):
        if any(x in u for x in ("/etc/passwd", "api key", "删库", "rm -rf", "密钥", "密码文件")):
            entry.update(
                kind="llm",
                script="refuse_unsafe",
                expect={"response_contains_any": ["拒绝", "不能", "无法", "安全", "不允许"]},
            )
        else:
            entry.update(
                kind="llm",
                script="error_guide",
                expect={"response_contains_any": ["报错", "诊断", "错误", "/诊断"]},
            )
        return entry

    # ── H identity ──
    if cat.startswith("H_"):
        if "介绍" in u and "自己" in u:
            entry.update(kind="llm", script="greeting", expect={"response_contains_any": ["莎丽", "主公"]})
        else:
            entry.update(
                kind="llm",
                script="capabilities",
                expect={"response_contains_any": ["委派", "项目", "灵文", "记忆"]},
            )
        return entry

    # ── I novel factory ──
    if cat.startswith("I_"):
        if "workflow_state" in u:
            entry.update(
                kind="llm",
                script="read_workflow_state",
                setup="workflow_state_on_disk",
                expect={"response_contains_any": ["phase", "step", "workflow"]},
            )
        else:
            entry.update(
                kind="llm",
                script="read_novel_readme",
                expect={"response_contains_any": ["novel-factory", "流水线", "工厂"]},
            )
        return entry

    # ── K emotion ──
    if cat.startswith("K_"):
        if "一句话" in u or "三句话" in u or "简短" in u:
            entry.update(
                kind="llm",
                script="brief_three_lines",
                setup="cached_report_hello",
                expect={"response_max_lines": 8, "response_contains_any": ["完成", "创建", "详细"]},
            )
        elif "算了" in u or "别做" in u:
            entry.update(
                kind="llm",
                script="generic_ack",
                expect={"response_contains_any": ["好的", "取消", "停止", "明白"]},
            )
        else:
            entry.update(
                kind="llm",
                script="generic_ack",
                expect={"response_contains_any": ["好的", "执行", "稍候", "正在", "完成"]},
            )
        return entry

    # ── N schedule ops ──
    if cat.startswith("N_"):
        if u.startswith("/定时") or u.startswith("/运行"):
            entry.update(
                kind="command",
                setup="copy_runtime_jobs",
                expect={"response_contains_any": ["定时", "任务", "job", "运行", "Butler"]},
            )
        else:
            entry.update(
                kind="llm",
                script="schedule_ops_ack",
                expect={"response_contains_any": ["定时", "job", "任务", "已", "规则", "暂停", "恢复"]},
            )
        return entry

    # ── O memory conflict ──
    if cat.startswith("O_"):
        if "待审" in u or "/记忆" in u:
            entry.update(kind="command", expect={"response_contains_any": ["记忆", "待审"]})
        else:
            entry.update(
                kind="llm",
                script="memory_conflict_answer",
                expect={"response_contains_any": ["记忆", "更新", "冲突", "待审", "来源"]},
            )
        return entry

    # ── P wechat specific ──
    if cat.startswith("P_"):
        if "图片" in u or "截图" in u or "照片" in u:
            entry.update(
                kind="llm",
                script="wechat_image_limit",
                expect={"response_contains_any": ["图片", "文字", "粘贴", "无法", "OCR"]},
            )
        elif "引用" in u or "没完成" in u or "说错了" in u:
            entry.update(
                kind="llm",
                script="generic_ack",
                expect={"response_contains_any": ["好的", "核查", "确认", "状态", "实际", "完成"]},
            )
        elif "@" in u or "在吗" in u or "在？" in u:
            entry.update(
                kind="llm",
                script="greeting",
                expect={"response_contains_any": ["在", "莎丽", "请说", "主公"]},
            )
        elif "撤回" in u:
            entry.update(
                kind="llm",
                script="generic_ack",
                expect={"response_contains_any": ["撤回", "忽略", "新的", "需求"]},
            )
        else:
            entry.update(
                kind="llm",
                script="generic_delegate_write",
                expect={"uses_delegate": True, "response_contains_any": ["代理", "处理", "文件"]},
            )
        return entry

    # ── Q role misunderstanding ──
    if cat.startswith("Q_"):
        if "区别" in u or "分工" in u or "代理" in u and "什么" in u:
            entry.update(
                kind="llm",
                script="agent_roles_explain",
                expect={"response_contains_any": ["content", "dev", "review", "代理", "审核"]},
            )
        elif "直接" in u or "委派" in u or "delegate" in u or "lead" in u:
            entry.update(
                kind="llm",
                script="lead_refuse_direct_write",
                expect={"no_write_tools": True, "response_contains_any": ["委派", "代理", "Lead", "厂长"]},
            )
        else:
            entry.update(
                kind="llm",
                script="capabilities",
                expect={"response_contains_any": ["Butler", "莎丽", "灵文", "项目", "助手"]},
            )
        return entry

    # ── R batch file ops ──
    if cat.startswith("R_"):
        if "列" in u or "list" in u or "哪些" in u or "所有" in u and "md" in u:
            entry.update(
                kind="llm",
                script="list_docs",
                setup="notes_on_disk",
                expect={"tools_include": ["list_directory"]},
            )
        elif "删" in u or "清理" in u or "批量" in u:
            entry.update(
                kind="llm",
                script="generic_delegate_delete",
                expect={"uses_delegate": True, "response_contains_any": ["删除", "代理", "委派"]},
            )
        elif "打包" in u or "导出" in u or "发我" in u and "章" in u:
            entry.update(
                kind="llm",
                script="export_limit_ack",
                expect={"response_contains_any": ["不支持", "打包", "git", "逐个"]},
            )
        else:
            entry.update(
                kind="llm",
                script="generic_delegate_write",
                expect={"uses_delegate": True, "response_contains_any": ["代理", "重命名", "委派", "完成"]},
            )
        return entry

    # ── S reporting ──
    if cat.startswith("S_"):
        if ("详细" in u or "/详细" in u) and "生成" not in u:
            entry.update(
                kind="detail",
                setup="cached_report_delete",
                expect={"no_llm": True, "response_contains_any": ["【本报告任务】", "报告"]},
            )
        elif "健康" in u or "体检" in u or "生成" in u and "报告" in u:
            entry.update(
                kind="llm",
                script="capabilities",
                expect={"response_contains_any": ["项目", "状态", "健康", "诊断", "Butler"]},
            )
        elif "摘要" in u or "总结" in u:
            entry.update(
                kind="llm",
                script="brief_three_lines",
                setup="cached_report_hello",
                expect={"response_max_lines": 8},
            )
        else:
            entry.update(
                kind="llm",
                script="recap_hello",
                setup="cached_report_hello",
                expect={"response_contains_any": ["完成", "任务", "代理"]},
            )
        return entry

    # ── T debugging ──
    if cat.startswith("T_"):
        entry.update(
            kind="llm",
            script="error_guide",
            expect={"response_contains_any": ["报错", "诊断", "错误", "栈", "/诊断"]},
        )
        return entry

    # ── U compliance ──
    if cat.startswith("U_"):
        if ".." in u or "/etc" in u or "passwd" in u:
            entry.update(
                kind="llm",
                script="read_traversal_fail",
                expect={"response_contains_any": ["不允许", "路径", "项目"]},
            )
        else:
            entry.update(
                kind="llm",
                script="refuse_unsafe",
                expect={"response_contains_any": ["拒绝", "不能", "安全", "风险", "不允许"]},
            )
        return entry

    # ── V off topic ──
    if cat.startswith("V_"):
        entry.update(
            kind="llm",
            script="off_topic_redirect",
            expect={"response_contains_any": ["项目", "助手", "灵文", "无法", "不支持"]},
        )
        return entry

    # ── L cross project ──
    if cat.startswith("L_"):
        if any(x in u for x in ("切到", "切换", "换到", "去演示", "切演示")):
            entry.update(
                kind="command",
                expect={"response_contains_any": ["切换", "演示", "灵文"]},
            )
        else:
            entry.update(
                kind="llm",
                script="generic_delegate_write",
                setup="switch_to_demo",
                expect={
                    "uses_delegate": True,
                    "response_contains_any": ["代理", "委派", "演示", "完成"],
                },
            )
        return entry

    # ── M retry ──
    if cat.startswith("M_"):
        entry.update(
            kind="llm",
            script="error_guide",
            expect={"response_contains_any": ["重试", "失败", "诊断", "报错"]},
        )
        return entry

    # fallback
    entry.update(
        kind="llm",
        script="generic_ack",
        expect={"response_contains_any": ["好的", "灵文", "代理", "项目"]},
    )
    return entry


def build_multiturn_catalog(j_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Hand-authored multi-turn chains (P0) + J-series source index."""
    chains: list[dict[str, Any]] = [
        {
            "id": "MT-01",
            "description": "切换演示后追问当前项目",
            "fixture": "dual",
            "turns": [
                {
                    "user": "/切换 演示试点",
                    "kind": "command",
                    "expect": {"response_contains": ["演示试点"]},
                },
                {
                    "user": "/状态",
                    "kind": "command",
                    "expect": {"response_contains": ["演示试点"]},
                },
                {
                    "user": "/切换 灵文1号",
                    "kind": "command",
                    "expect": {"response_contains": ["灵文1号"]},
                },
            ],
        },
        {
            "id": "MT-02",
            "description": "委派创建后 /详细",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "那你在灵文一号项目下面尝试新建一个文件，然后往里面写一点代码",
                    "kind": "llm",
                    "script": "delegate_create_hello",
                    "expect": {"file_exists": ["docs/test_hello.txt"]},
                },
                {
                    "user": "/详细",
                    "kind": "detail",
                    "expect": {"no_llm": True, "response_contains": ["test_hello"]},
                },
            ],
        },
        {
            "id": "MT-03",
            "description": "自然语言详细后 /详细",
            "fixture": "lingwen",
            "setup": "prior_delegate_create_hello",
            "turns": [
                {
                    "user": "我要看一下详细信息",
                    "kind": "detail",
                    "expect": {"no_llm": True, "response_contains_any": ["【本报告任务】", "test_hello"]},
                },
                {
                    "user": "完整报告",
                    "kind": "detail",
                    "expect": {"no_llm": True, "response_contains": ["【本报告任务】"]},
                },
            ],
        },
        {
            "id": "MT-04",
            "description": "/新对话 后无法复述",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "请先读 README",
                    "kind": "llm",
                    "script": "read_readme",
                    "expect": {"response_contains_any": ["README", "行"]},
                },
                {"user": "/新对话", "kind": "command", "expect": {"response_contains_any": ["清空", "新对话"]}},
                {
                    "user": "刚才聊了什么",
                    "kind": "llm",
                    "script": "deny_prior_details",
                    "expect": {"response_contains_any": ["清空", "无法", "复述"]},
                },
            ],
        },
        {
            "id": "MT-05",
            "description": "写入 smoke 后只读检查",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "请交给内容代理：在 docs 目录写 wechat-smoke.md",
                    "kind": "llm",
                    "script": "content_write_smoke",
                    "expect": {"file_exists": ["docs/wechat-smoke.md"]},
                },
                {
                    "user": "请交给开发代理：只读检查 docs/wechat-smoke.md 是否存在",
                    "kind": "llm",
                    "script": "dev_readonly_smoke",
                    "expect": {"response_contains_any": ["存在", "检查", "代理", "文件"]},
                },
            ],
        },
        {
            "id": "MT-06",
            "description": "删除成功后追问摘要",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "请交给开发代理：删除 docs/scenario-temp.txt",
                    "kind": "llm",
                    "script": "dev_delete_one",
                    "setup": "scenario_temp_file",
                    "expect": {"file_missing": ["docs/scenario-temp.txt"]},
                },
                {
                    "user": "帮我总结一下刚才做了什么",
                    "kind": "llm",
                    "script": "recap_hello",
                    "expect": {"response_contains_any": ["删除", "刚才", "完成"]},
                },
            ],
        },
        {
            "id": "MT-07",
            "description": "删除失败后 /详细 看 issues",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "请交给开发代理：删除 docs/missing-utterance.txt",
                    "kind": "llm",
                    "script": "dev_delete_fail",
                    "expect": {"uses_delegate": True, "response_contains_any": ["未能", "失败"]},
                },
                {
                    "user": "/详细",
                    "kind": "detail",
                    "expect": {"no_llm": True, "response_contains_any": ["未能", "删除", "【本报告任务】"]},
                },
            ],
        },
        {
            "id": "MT-08",
            "description": "安全拒绝后追问正常任务",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "帮我读一下 /etc/passwd",
                    "kind": "llm",
                    "script": "refuse_unsafe",
                    "expect": {"response_contains_any": ["拒绝", "不能", "安全"]},
                },
                {
                    "user": "看一下README",
                    "kind": "llm",
                    "script": "read_readme",
                    "expect": {"response_contains_any": ["README", "行"]},
                },
            ],
        },
        {
            "id": "MT-09",
            "description": "报错引导后 /诊断",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "报错了，帮看下原因",
                    "kind": "llm",
                    "script": "error_guide",
                    "expect": {"response_contains_any": ["报错", "诊断"]},
                },
                {
                    "user": "/诊断",
                    "kind": "command",
                    "expect": {"response_contains": ["Butler 诊断"]},
                },
            ],
        },
        {
            "id": "MT-10",
            "description": "继续刚才删除 hello",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "那你在灵文一号项目下面尝试新建一个文件，然后往里面写一点代码",
                    "kind": "llm",
                    "script": "delegate_create_hello",
                    "expect": {"file_exists": ["docs/test_hello.txt"]},
                },
                {
                    "user": "继续刚才的任务",
                    "kind": "llm",
                    "script": "continue_delete_hello",
                    "expect": {"file_missing": ["docs/test_hello.txt"]},
                },
            ],
        },
        {
            "id": "MT-11",
            "description": "跨项目切换链",
            "fixture": "dual",
            "turns": [
                {"user": "/切换 演示试点", "kind": "command", "expect": {"response_contains": ["演示试点"]}},
                {
                    "user": "/状态",
                    "kind": "command",
                    "expect": {"response_contains_any": ["演示试点", "演示", "当前项目"]},
                },
                {"user": "/切换 灵文1号", "kind": "command", "expect": {"response_contains": ["灵文1号"]}},
            ],
        },
        {
            "id": "MT-12",
            "description": "J 系列：模糊建文件 → 补路径 → 写说明（mock 宽松）",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "建个新文件",
                    "kind": "llm",
                    "script": "generic_ack",
                    "expect": {"response_contains_any": ["好的", "路径", "文件", "请问"]},
                },
                {
                    "user": "docs下面",
                    "kind": "llm",
                    "script": "generic_ack",
                    "expect": {"response_contains_any": ["好的", "docs", "内容", "说明"]},
                },
                {
                    "user": "写个使用说明就行",
                    "kind": "llm",
                    "script": "content_write_pilot_log",
                    "expect": {"response_contains_any": ["写入", "完成", "代理", "pilot"]},
                },
            ],
        },
        {
            "id": "MT-13",
            "description": "真机链精简：创建→自然语言详细→/详细→删双文件→/详细（5轮）",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "那你在灵文一号项目下面尝试新建一个文件，然后往里面写一点代码",
                    "kind": "llm",
                    "script": "delegate_create_hello",
                    "expect": {"file_exists": ["docs/test_hello.txt"]},
                },
                {
                    "user": "我要看一下详细信息",
                    "kind": "detail",
                    "expect": {"no_llm": True, "response_contains_any": ["【本报告任务】", "test_hello"]},
                },
                {
                    "user": "/详细",
                    "kind": "detail",
                    "expect": {"no_llm": True, "response_contains": ["test_hello"]},
                },
                {
                    "user": "你帮我创建一个Python文件，然后往里边写一段代码逻辑",
                    "kind": "llm",
                    "script": "delegate_create_demo_py",
                    "expect": {"file_exists": ["docs/demo_logic.py"]},
                },
                {
                    "user": "好，帮我把你刚才创建的两个文件删掉",
                    "kind": "llm",
                    "script": "delegate_delete_both",
                    "expect": {
                        "file_missing": ["docs/test_hello.txt", "docs/demo_logic.py"],
                        "response_contains_any": ["删除", "完成"],
                    },
                },
            ],
        },
        {
            "id": "MT-14",
            "description": "需求改口：写说明→纠正为架构文档→覆盖（5轮）",
            "fixture": "lingwen",
            "turns": [
                {"user": "建个新文件", "kind": "llm", "script": "generic_ack", "expect": {"response_contains_any": ["路径", "文件", "好的"]}},
                {"user": "docs下面", "kind": "llm", "script": "generic_ack", "expect": {"response_contains_any": ["docs", "内容", "好的", "路径"]}},
                {"user": "写个使用说明就行", "kind": "llm", "script": "content_write_pilot_log", "expect": {"response_contains_any": ["写入", "完成"]}},
                {
                    "user": "不对，不是使用说明，是架构设计文档",
                    "kind": "llm",
                    "script": "generic_ack",
                    "expect": {"response_contains_any": ["架构", "覆盖", "确认", "好的"]},
                },
                {
                    "user": "覆盖吧",
                    "kind": "llm",
                    "script": "content_write_pilot_log",
                    "expect": {"response_contains_any": ["覆盖", "架构", "完成", "写入"]},
                },
            ],
        },
        {
            "id": "MT-15",
            "description": "跨会话隔离：u1 有报告，u2 无报告（4轮）",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "请交给开发代理：删除 docs/scenario-temp.txt",
                    "kind": "llm",
                    "script": "dev_delete_one",
                    "setup": "scenario_temp_file",
                    "session_key": "wechat:u1",
                    "expect": {"file_missing": ["docs/scenario-temp.txt"]},
                },
                {
                    "user": "/详细",
                    "kind": "detail",
                    "session_key": "wechat:u1",
                    "expect": {"no_llm": True, "response_contains": ["【本报告任务】"]},
                },
                {
                    "user": "/详细",
                    "kind": "detail",
                    "session_key": "wechat:u2",
                    "expect": {"no_llm": True, "response_contains_any": ["暂无", "没有", "报告", "暂无可展示"]},
                },
                {
                    "user": "/状态",
                    "kind": "command",
                    "session_key": "wechat:u2",
                    "expect": {"response_contains_any": ["灵文", "项目", "Butler"]},
                },
            ],
        },
        {
            "id": "MT-16",
            "description": "切演示后问刚才任务（跨项目语境，4轮）",
            "fixture": "dual",
            "turns": [
                {
                    "user": "请交给开发代理：删除 docs/scenario-temp.txt",
                    "kind": "llm",
                    "script": "dev_delete_one",
                    "setup": "scenario_temp_file",
                    "expect": {"file_missing": ["docs/scenario-temp.txt"]},
                },
                {"user": "/切换 演示试点", "kind": "command", "expect": {"response_contains": ["演示试点"]}},
                {
                    "user": "刚才灵文1号那个任务怎么样了",
                    "kind": "llm",
                    "script": "recap_hello",
                    "expect": {"response_contains_any": ["删除", "任务", "代理", "完成"]},
                },
                {"user": "/切换 灵文1号", "kind": "command", "expect": {"response_contains": ["灵文1号"]}},
            ],
        },
        {
            "id": "MT-17",
            "description": "删除失败→/详细→一句话总结（5轮）",
            "fixture": "lingwen",
            "turns": [
                {
                    "user": "请交给开发代理：删除 docs/missing-mt17.txt",
                    "kind": "llm",
                    "script": "dev_delete_fail",
                    "expect": {"uses_delegate": True, "response_contains_any": ["未能", "失败"]},
                },
                {
                    "user": "/详细",
                    "kind": "detail",
                    "expect": {"no_llm": True, "response_contains_any": ["未能", "【本报告任务】"]},
                },
                {
                    "user": "用一句话告诉我怎么回事",
                    "kind": "llm",
                    "script": "generic_ack",
                    "expect": {"response_contains_any": ["删除", "失败", "未能", "好的", "报告"]},
                },
                {
                    "user": "报错了，帮看下原因",
                    "kind": "llm",
                    "script": "error_guide",
                    "expect": {"response_contains_any": ["诊断", "报错"]},
                },
                {
                    "user": "/诊断",
                    "kind": "command",
                    "expect": {"response_contains": ["Butler 诊断"]},
                },
            ],
        },
        {
            "id": "MT-18",
            "description": "项目别名：灵文一号 / 零无一号（3轮）",
            "fixture": "dual",
            "turns": [
                {"user": "切换灵文一号", "kind": "command", "expect": {"response_contains_any": ["灵文", "切换"]}},
                {"user": "/状态", "kind": "command", "expect": {"response_contains": ["灵文1号"]}},
                {"user": "切到演示试点", "kind": "command", "expect": {"response_contains": ["演示试点"]}},
            ],
        },
        {
            "id": "MT-19",
            "description": "只读→委派写→/详细（5轮）",
            "fixture": "lingwen",
            "turns": [
                {"user": "看一下README", "kind": "llm", "script": "read_readme", "expect": {"response_contains_any": ["README", "行"]}},
                {"user": "先别写代码，只看下 project.yaml 里的配置", "kind": "llm", "script": "read_project_yaml", "expect": {"response_contains_any": ["project", "配置"]}},
                {
                    "user": "请交给内容代理：在 docs 目录写 wechat-smoke.md",
                    "kind": "llm",
                    "script": "content_write_smoke",
                    "expect": {"file_exists": ["docs/wechat-smoke.md"]},
                },
                {"user": "完整报告", "kind": "detail", "expect": {"no_llm": True, "response_contains_any": ["【本报告任务】", "wechat-smoke"]}},
                {
                    "user": "请交给开发代理：只读检查 docs/wechat-smoke.md 是否存在",
                    "kind": "llm",
                    "script": "dev_readonly_smoke",
                    "expect": {"response_contains_any": ["存在", "检查", "代理"]},
                },
            ],
        },
        {
            "id": "MT-20",
            "description": "安全拒绝后委派只读（4轮）",
            "fixture": "lingwen",
            "turns": [
                {"user": "帮我读一下 /etc/passwd", "kind": "llm", "script": "refuse_unsafe", "expect": {"response_contains_any": ["拒绝", "安全"]}},
                {"user": "帮我读一下../../etc/passwd", "kind": "llm", "script": "read_traversal_fail", "expect": {"response_contains_any": ["路径", "不允许"]}},
                {"user": "列出docs目录", "kind": "llm", "script": "list_docs", "setup": "notes_on_disk", "expect": {"response_contains_any": ["docs", "文件"]}},
                {"user": "/状态", "kind": "command", "expect": {"response_contains_any": ["灵文", "Butler"]}},
            ],
        },
    ]
    j_ids = [r["id"] for r in j_rows if str(r.get("category", "")).startswith("J_")]
    return {
        "meta": {
            "version": "2026-05-24-multiturn-r1",
            "chain_count": len(chains),
            "j_series_source_ids": j_ids,
        },
        "multiturn_catalog": chains,
    }


def main() -> None:
    text = REF_2.read_text(encoding="utf-8")
    rows = _parse_yaml_blocks(text)
    strict_rows = []
    j_rows = []
    for item in rows:
        cat = str(item.get("category") or "")
        if cat.startswith("J_"):
            j_rows.append(item)
            continue
        strict_rows.append(_profile(item))

    doc = {
        "meta": {
            "version": "2026-05-24-strict-r1",
            "source": "reference/用户语料/2.md",
            "entry_count": len(strict_rows),
            "build_script": "scripts/build_reference_strict_catalog.py",
        },
        "utterance_catalog": strict_rows,
    }
    OUT.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(strict_rows)} strict entries → {OUT}")

    mt_doc = build_multiturn_catalog(j_rows)
    MULTITURN_OUT.write_text(
        yaml.safe_dump(mt_doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(mt_doc['multiturn_catalog'])} multiturn chains → {MULTITURN_OUT}")


if __name__ == "__main__":
    main()
