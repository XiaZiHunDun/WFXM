"""v3.0 LLM-in-loop 前提验证: P-PIM / P1-LIVE / P6-LIVE.

需要实际 LLM API 调用。通过 ``BUTLER_RUN_REAL_API_SMOKE=1`` 门控。

运行:
    source .env && BUTLER_RUN_REAL_API_SMOKE=1 \
      PYTHONPATH=. pytest -m live_llm tests/test_premise_v3_llm_live.py -v --tb=short

P-PIM: 50 条真实指令 × 2 provider → 意图路由准确率
P1-LIVE: 20 条指令 × 2 provider → 工具调用 parse 成功率
P6-LIVE: 10 段 transcript → 事实提取覆盖率
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.live_llm


# ── 公共基础设施 ────────────────────────────────────────────


def _require_smoke():
    if os.getenv("BUTLER_RUN_REAL_API_SMOKE") != "1":
        pytest.skip("set BUTLER_RUN_REAL_API_SMOKE=1")


def _make_client(provider: str, *, max_tokens: int = 512, timeout: int = 90):
    from butler.transport.llm_client import LLMClient
    from butler.transport.providers import get_provider

    _require_smoke()
    profile = get_provider(provider)
    if profile is None:
        pytest.skip(f"unknown provider: {provider}")
    api_key = profile.resolve_api_key()
    if not api_key:
        pytest.skip(f"no API key for {provider}")

    model_env = f"BUTLER_SMOKE_{provider.upper()}_MODEL"
    model = os.getenv(model_env, profile.default_model).strip()
    return LLMClient(
        provider=provider,
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        timeout=timeout,
    )


def _get_pim_tools() -> list[dict]:
    """获取完整的 PIM 工具 schema 列表。"""
    from butler.tools.registry import _ensure_builtins, _REGISTRY
    from butler.tools.pim_schema import ALL_PIM_TOOLS

    _ensure_builtins()
    tools = []
    for name in sorted(ALL_PIM_TOOLS):
        entry = _REGISTRY.get(name)
        if entry:
            tools.append({
                "type": "function",
                "function": {
                    "name": entry.name,
                    "description": entry.description,
                    "parameters": entry.schema,
                },
            })
    tools.append({
        "type": "function",
        "function": {
            "name": "butler_remember",
            "description": "记住用户的个人偏好、习惯或经验教训",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["owner_profile", "owner_experience", "project_notes"],
                    },
                    "content": {"type": "string"},
                },
                "required": ["scope", "content"],
            },
        },
    })
    return tools


# ══════════════════════════════════════════════════════════════
#  P-PIM: PIM 意图路由准确率（50 条指令 × 2 provider）
# ══════════════════════════════════════════════════════════════


_PIM_ROUTING_CASES: list[tuple[str, str]] = [
    # (用户指令, 期望工具名)
    # ── memo_add ──
    ("帮我记一下明天下午3点开会", "memo_add"),
    ("添加备忘：周五交项目报告", "memo_add"),
    ("记一下，下周一需要体检", "memo_add"),
    ("帮我加个待办，买机票", "memo_add"),
    ("添加一个备忘录，还信用卡", "memo_add"),
    ("记一下生日派对在周六", "memo_add"),
    ("帮我建一个待办事项：准备演讲稿", "memo_add"),
    # ── contact_add ──
    ("帮我存一下张三的电话 13812345678", "contact_add"),
    ("保存联系人 李四 邮箱 lisi@example.com", "contact_add"),
    ("记下王五的地址：北京市海淀区", "contact_add"),
    ("存一下陈六的手机号 13900001111", "contact_add"),
    ("添加联系人 赵七 电话 18612345678 工作", "contact_add"),
    # ── expense_add ──
    ("午饭花了45块", "expense_add"),
    ("今天打车花了30元", "expense_add"),
    ("记账：超市购物 200 元", "expense_add"),
    ("刚才咖啡花了28块", "expense_add"),
    ("本月房租 3500 已付", "expense_add"),
    ("电影票两张 80 元", "expense_add"),
    ("记一笔支出，理发 50 元", "expense_add"),
    # ── habit_create ──
    ("帮我创建一个每日喝水打卡", "habit_create"),
    ("建一个运动习惯，每周三次", "habit_create"),
    ("创建习惯：每天早起", "habit_create"),
    ("我想养成阅读的习惯", "habit_create"),
    # ── set_reminder ──
    ("30分钟后提醒我喝水", "set_reminder"),
    ("明天早上9点提醒我开会", "set_reminder"),
    ("2小时后提醒我吃药", "set_reminder"),
    ("提醒我下午5点接孩子", "set_reminder"),
    ("每天早上8点提醒我运动", "set_reminder"),
    ("一小时后提醒我回复邮件", "set_reminder"),
    ("每周一提醒我交周报", "set_reminder"),
    # ── butler_remember ──
    ("记住，我喜欢喝美式咖啡", "butler_remember"),
    ("帮我记住，我习惯11点睡觉", "butler_remember"),
    ("记住我不吃辣", "butler_remember"),
    ("我偏好用 TypeScript 写前端代码", "butler_remember"),
    ("记住我的代码规范是两空格缩进", "butler_remember"),
    # ── memo_list / memo_search ──
    ("看看我的备忘录", "memo_list"),
    ("搜索购物相关的备忘", "memo_search"),
    # ── contact_find ──
    ("查一下张三的电话", "contact_find"),
    ("找一下李四的联系方式", "contact_find"),
    # ── expense_summary ──
    ("这个月花了多少钱", "expense_summary"),
    ("看看本月支出汇总", "expense_summary"),
    # ── expense_list ──
    ("最近的支出明细", "expense_list"),
    # ── habit_checkin ──
    ("喝水打卡", "habit_checkin"),
    ("运动打卡完成", "habit_checkin"),
    # ── habit_stats ──
    ("看看我的打卡情况", "habit_stats"),
    # ── list_reminders ──
    ("看看我的提醒", "list_reminders"),
    # ── contact_list ──
    ("列出所有联系人", "contact_list"),
    # ── habit_list ──
    ("我有哪些习惯", "habit_list"),
    # ── memo_update ──
    ("把那个开会备忘改成周四", "memo_update"),
    # ── expense_search ──
    ("搜索上个月的餐饮支出", "expense_search"),
]

assert len(_PIM_ROUTING_CASES) == 50, f"Expected 50 cases, got {len(_PIM_ROUTING_CASES)}"

_PIM_SYSTEM_PROMPT = """你是一个 AI 管家。根据用户指令，选择最合适的工具来处理请求。

关键路由规则：
- 用户说「帮我记一下明天开会」→ memo_add（结构化待办），如有明确时间可同时 set_reminder
- 用户说「N分钟/小时后提醒我…」「明天X点提醒我…」→ set_reminder（定时推送），不是 memo_add
- 用户说「记住我喜欢喝美式咖啡」→ butler_remember（个人偏好），不是 memo_add
- 用户说「存一下张三电话」→ contact_add
- 用户说「午饭花了30块」→ expense_add
- 用户说「打卡」→ habit_checkin
- 用户说「创建习惯」→ habit_create
- 用户说「看看/列出/查询备忘/联系人/支出/习惯/提醒」→ 对应的 *_list / *_search / *_find / *_stats / *_summary
- 用户说「修改/改一下」→ 对应的 *_update

你必须调用工具来处理请求，不要只口头回复。"""


def _run_pim_routing_test(provider: str) -> dict:
    """运行 PIM 路由准确率测试，返回详细结果。"""
    client = _make_client(provider, max_tokens=256, timeout=60)
    tools = _get_pim_tools()

    from butler.transport.schema_sanitizer import sanitize_tool_schemas
    sanitized = sanitize_tool_schemas(tools)

    results = {"correct": 0, "wrong": 0, "no_tool": 0, "errors": 0, "details": []}

    for instruction, expected_tool in _PIM_ROUTING_CASES:
        try:
            response = client.complete(
                messages=[
                    {"role": "system", "content": _PIM_SYSTEM_PROMPT},
                    {"role": "user", "content": instruction},
                ],
                tools=sanitized,
            )

            tool_calls = response.tool_calls or []
            if not tool_calls:
                results["no_tool"] += 1
                results["details"].append({
                    "instruction": instruction,
                    "expected": expected_tool,
                    "actual": None,
                    "status": "no_tool",
                })
                continue

            tc = tool_calls[0]
            actual_tool = tc.name if hasattr(tc, "name") else ""
            if actual_tool == expected_tool:
                results["correct"] += 1
                status = "correct"
            else:
                results["wrong"] += 1
                status = "wrong"

            results["details"].append({
                "instruction": instruction,
                "expected": expected_tool,
                "actual": actual_tool,
                "status": status,
            })

        except Exception as exc:
            results["errors"] += 1
            results["details"].append({
                "instruction": instruction,
                "expected": expected_tool,
                "actual": f"ERROR: {exc}",
                "status": "error",
            })

    total = len(_PIM_ROUTING_CASES)
    results["total"] = total
    results["accuracy"] = results["correct"] / total if total > 0 else 0
    return results


class TestPPIMLiveRouting:
    """P-PIM: 50 条真实指令 × 2 provider 意图路由准确率。"""

    def test_minimax_pim_routing_accuracy(self):
        results = _run_pim_routing_test("minimax")
        accuracy = results["accuracy"]
        total = results["total"]
        correct = results["correct"]

        wrongs = [d for d in results["details"] if d["status"] in ("wrong", "no_tool")]
        wrong_summary = "; ".join(
            f"'{d['instruction'][:20]}' expect={d['expected']} got={d['actual']}"
            for d in wrongs[:5]
        )

        assert accuracy >= 0.85, (
            f"MiniMax PIM routing accuracy {accuracy:.1%} ({correct}/{total}) < 85%. "
            f"Errors: {wrong_summary}"
        )

    def test_deepseek_pim_routing_accuracy(self):
        results = _run_pim_routing_test("deepseek")
        accuracy = results["accuracy"]
        total = results["total"]
        correct = results["correct"]

        wrongs = [d for d in results["details"] if d["status"] in ("wrong", "no_tool")]
        wrong_summary = "; ".join(
            f"'{d['instruction'][:20]}' expect={d['expected']} got={d['actual']}"
            for d in wrongs[:5]
        )

        assert accuracy >= 0.85, (
            f"DeepSeek PIM routing accuracy {accuracy:.1%} ({correct}/{total}) < 85%. "
            f"Errors: {wrong_summary}"
        )


# ══════════════════════════════════════════════════════════════
#  P1-LIVE: LLM 工具调用 parse 成功率（20 条 × 2 provider）
# ══════════════════════════════════════════════════════════════


_P1_TOOL_CALL_CASES: list[tuple[str, str]] = [
    ("帮我存一下张三电话 13800138000", "contact_add"),
    ("添加备忘：周五开会", "memo_add"),
    ("午餐花了35块", "expense_add"),
    ("创建每日跑步习惯", "habit_create"),
    ("10分钟后提醒我喝水", "set_reminder"),
    ("记住我不吃香菜", "butler_remember"),
    ("搜索上周的备忘", "memo_search"),
    ("张三的电话号码是多少", "contact_find"),
    ("本月支出多少", "expense_summary"),
    ("看看打卡记录", "habit_stats"),
    ("我的提醒列表", "list_reminders"),
    ("列出所有联系人", "contact_list"),
    ("看看我的习惯", "habit_list"),
    ("查看最近的备忘录", "memo_list"),
    ("最近有哪些花销", "expense_list"),
    ("存联系人 王五 18612345678", "contact_add"),
    ("记账 水电费 300 元", "expense_add"),
    ("2小时后提醒我给李四打电话", "set_reminder"),
    ("帮我记一下后天交房租", "memo_add"),
    ("记住我的编码风格是 4 空格缩进", "butler_remember"),
]

assert len(_P1_TOOL_CALL_CASES) == 20


def _run_p1_tool_call_test(provider: str) -> dict:
    """测试工具调用是否能成功 parse（有效 tool_call 结构）。"""
    client = _make_client(provider, max_tokens=256, timeout=60)
    tools = _get_pim_tools()
    from butler.transport.schema_sanitizer import sanitize_tool_schemas
    sanitized = sanitize_tool_schemas(tools)

    results = {"parsed": 0, "no_tool": 0, "bad_json": 0, "errors": 0, "details": []}

    for instruction, expected_tool in _P1_TOOL_CALL_CASES:
        try:
            response = client.complete(
                messages=[
                    {"role": "system", "content": _PIM_SYSTEM_PROMPT},
                    {"role": "user", "content": instruction},
                ],
                tools=sanitized,
            )

            tool_calls = response.tool_calls or []
            if not tool_calls:
                results["no_tool"] += 1
                results["details"].append({
                    "instruction": instruction,
                    "status": "no_tool",
                })
                continue

            tc = tool_calls[0]
            name = tc.name if hasattr(tc, "name") else ""
            args_raw = tc.arguments if hasattr(tc, "arguments") else ""

            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                if isinstance(args, dict):
                    results["parsed"] += 1
                    results["details"].append({
                        "instruction": instruction,
                        "tool": name,
                        "args": args,
                        "status": "parsed",
                    })
                else:
                    results["bad_json"] += 1
                    results["details"].append({
                        "instruction": instruction,
                        "status": "bad_json",
                        "raw": str(args_raw)[:100],
                    })
            except (json.JSONDecodeError, TypeError):
                results["bad_json"] += 1
                results["details"].append({
                    "instruction": instruction,
                    "status": "bad_json",
                    "raw": str(args_raw)[:100],
                })

        except Exception as exc:
            results["errors"] += 1
            results["details"].append({
                "instruction": instruction,
                "status": "error",
                "error": str(exc)[:200],
            })

    total = len(_P1_TOOL_CALL_CASES)
    results["total"] = total
    results["parse_rate"] = results["parsed"] / total if total > 0 else 0
    return results


class TestP1LiveToolCall:
    """P1-LIVE: 20 条指令 × 2 provider 工具调用 parse 成功率。"""

    def test_minimax_tool_call_parse_rate(self):
        results = _run_p1_tool_call_test("minimax")
        rate = results["parse_rate"]
        parsed = results["parsed"]
        total = results["total"]

        failures = [d for d in results["details"] if d["status"] != "parsed"]
        fail_summary = "; ".join(
            f"'{d['instruction'][:20]}' status={d['status']}"
            for d in failures[:5]
        )

        assert rate >= 0.90, (
            f"MiniMax tool parse rate {rate:.1%} ({parsed}/{total}) < 90%. "
            f"Failures: {fail_summary}"
        )

    def test_deepseek_tool_call_parse_rate(self):
        results = _run_p1_tool_call_test("deepseek")
        rate = results["parse_rate"]
        parsed = results["parsed"]
        total = results["total"]

        failures = [d for d in results["details"] if d["status"] != "parsed"]
        fail_summary = "; ".join(
            f"'{d['instruction'][:20]}' status={d['status']}"
            for d in failures[:5]
        )

        assert rate >= 0.90, (
            f"DeepSeek tool parse rate {rate:.1%} ({parsed}/{total}) < 90%. "
            f"Failures: {fail_summary}"
        )


# ══════════════════════════════════════════════════════════════
#  P6-LIVE: Post-session 提取实测（10 段 transcript）
# ══════════════════════════════════════════════════════════════


_P6_TRANSCRIPTS: list[dict[str, Any]] = [
    {
        "messages": [
            {"role": "user", "content": "帮我把项目的数据库从 MySQL 迁移到 PostgreSQL"},
            {"role": "assistant", "content": "好的，我来帮你制定迁移方案。决定：使用 PostgreSQL 作为新的数据库引擎，主要原因是 JSONB 支持和更好的并发性能。"},
            {"role": "user", "content": "好的，先从 users 表开始迁移"},
            {"role": "assistant", "content": "已完成 users 表的 schema 迁移和数据导入，共迁移 15000 条记录。"},
        ],
        "expected_types": ["decision", "completion"],
        "min_facts": 1,
    },
    {
        "messages": [
            {"role": "user", "content": "不要在代码里用 var，请一律使用 const 或 let"},
            {"role": "assistant", "content": "明白了，我会遵循这个规范。"},
            {"role": "user", "content": "另外，我希望所有函数都写 JSDoc 注释"},
            {"role": "assistant", "content": "好的，这两条编码规范已经记录。"},
        ],
        "expected_types": ["user_preference"],
        "min_facts": 1,
    },
    {
        "messages": [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc1", "type": "function",
                 "function": {"name": "write_file", "arguments": '{"path":"src/config.py"}'}},
            ]},
            {"role": "tool", "tool_call_id": "tc1",
             "content": json.dumps({"ok": True, "path": "src/config.py", "action": "patch"})},
            {"role": "assistant", "content": "已完成 配置文件的重构，从环境变量读取所有敏感配置"},
        ],
        "expected_types": ["file_change", "completion"],
        "min_facts": 1,
    },
    {
        "messages": [
            {"role": "user", "content": "我们的前端选择了 React + TypeScript 的技术栈"},
            {"role": "assistant", "content": "结论：前端技术栈确定为 React + TypeScript，搭配 Tailwind CSS 做样式方案。"},
            {"role": "user", "content": "对，Tailwind 也用上"},
            {"role": "assistant", "content": "好的，已记录技术栈决策。"},
        ],
        "expected_types": ["decision"],
        "min_facts": 1,
    },
    {
        "messages": [
            {"role": "user", "content": "帮我检查一下 API 的性能"},
            {"role": "assistant", "content": "已完成 API 性能压测，P99 延迟从 850ms 优化到 120ms"},
            {"role": "user", "content": "太好了，部署到生产环境吧"},
            {"role": "assistant", "content": "已完成 生产环境部署，版本 v2.1.0 已上线"},
        ],
        "expected_types": ["completion"],
        "min_facts": 2,
    },
    {
        "messages": [
            {"role": "user", "content": "我想用微服务架构来设计后端"},
            {"role": "assistant", "content": "决定：采用微服务架构，将系统拆分为用户服务、订单服务和支付服务三个独立服务"},
            {"role": "user", "content": "服务间通信用 gRPC"},
            {"role": "assistant", "content": "确认：服务间通信采用 gRPC 协议，API 网关使用 REST"},
        ],
        "expected_types": ["decision"],
        "min_facts": 1,
    },
    {
        "messages": [
            {"role": "user", "content": "不要自动格式化 Python 代码，我用 black 手动格式化"},
            {"role": "assistant", "content": "好的，我不会在保存时自动格式化 Python 代码。"},
            {"role": "user", "content": "我喜欢简洁的日志输出，别打太多 debug 信息"},
            {"role": "assistant", "content": "已了解。日志级别保持 INFO，减少不必要的 debug 输出。"},
        ],
        "expected_types": ["user_preference"],
        "min_facts": 1,
    },
    {
        "messages": [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc2", "type": "function",
                 "function": {"name": "write_file", "arguments": '{"path":"tests/test_auth.py"}'}},
            ]},
            {"role": "tool", "tool_call_id": "tc2",
             "content": json.dumps({"ok": True, "path": "tests/test_auth.py"})},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc3", "type": "function",
                 "function": {"name": "write_file", "arguments": '{"path":"src/auth/handler.py"}'}},
            ]},
            {"role": "tool", "tool_call_id": "tc3",
             "content": json.dumps({"ok": True, "path": "src/auth/handler.py", "action": "patch"})},
            {"role": "assistant", "content": "已完成 认证模块的测试和实现代码更新"},
        ],
        "expected_types": ["file_change"],
        "min_facts": 1,
    },
    {
        "messages": [
            {"role": "user", "content": "选择了 PostgreSQL 而不是 MongoDB"},
            {"role": "assistant", "content": "决定：使用 PostgreSQL 作为主数据库，因为数据模型是结构化的，关系型数据库更适合当前需求"},
            {"role": "user", "content": "缓存层还是用 Redis"},
            {"role": "assistant", "content": "确认：缓存层使用 Redis，用于会话存储和热数据缓存。已完成 Redis 集群配置。"},
        ],
        "expected_types": ["decision", "completion"],
        "min_facts": 1,
    },
    {
        "messages": [
            {"role": "user", "content": "我需要每次提交前都跑 lint"},
            {"role": "assistant", "content": "好的，已完成 pre-commit hook 配置，每次 git commit 会自动跑 eslint 和 prettier"},
            {"role": "user", "content": "禁止直接 push 到 main 分支"},
            {"role": "assistant", "content": "决定：main 分支设为保护分支，所有变更必须通过 PR 和至少一个 review"},
        ],
        "expected_types": ["completion", "decision", "user_preference"],
        "min_facts": 1,
    },
]

assert len(_P6_TRANSCRIPTS) == 10


@pytest.fixture(autouse=True)
def _isolate_butler_home_llm(tmp_path, monkeypatch):
    home = tmp_path / ".butler"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("BUTLER_HOME", str(home))
    monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "1")
    from butler.config import reload_butler_settings
    reload_butler_settings()
    yield


class TestP6LiveFactExtraction:
    """P6-LIVE: 10 段 transcript × 独立 GT 事实提取覆盖率。

    注意：这里测试的是 heuristic fact extraction（不需要 LLM），
    因为 extract_pre_compact_facts 是基于正则的。
    同时也测试 LLM post-session processor 的可调用性。
    """

    def test_heuristic_fact_extraction_coverage(self):
        """验证 heuristic 提取对 10 段 transcript 的覆盖率。"""
        from butler.core.fact_extraction import _extract_facts_from_messages

        total_transcripts = len(_P6_TRANSCRIPTS)
        transcripts_with_facts = 0
        type_coverage = {"decision": 0, "completion": 0, "user_preference": 0, "file_change": 0}
        all_details = []

        for i, case in enumerate(_P6_TRANSCRIPTS):
            facts = _extract_facts_from_messages(case["messages"])
            found_types = {f["type"] for f in facts}

            hit = len(facts) >= case["min_facts"]
            if hit:
                transcripts_with_facts += 1

            for ft in found_types:
                if ft in type_coverage:
                    type_coverage[ft] += 1

            expected_hit = bool(found_types & set(case["expected_types"]))
            all_details.append({
                "transcript": i + 1,
                "expected_types": case["expected_types"],
                "found_types": list(found_types),
                "fact_count": len(facts),
                "expected_hit": expected_hit,
            })

        coverage = transcripts_with_facts / total_transcripts
        missed = [d for d in all_details if not d["expected_hit"]]
        miss_summary = "; ".join(
            f"T{d['transcript']}(expect={d['expected_types']}, got={d['found_types']})"
            for d in missed[:5]
        )

        assert coverage >= 0.80, (
            f"Fact extraction coverage {coverage:.1%} "
            f"({transcripts_with_facts}/{total_transcripts}) < 80%. "
            f"Missed: {miss_summary}"
        )

    def test_heuristic_extraction_precision(self):
        """验证提取的事实是否对应到正确的类型。"""
        from butler.core.fact_extraction import _extract_facts_from_messages

        total_facts = 0
        correct_type_facts = 0

        for case in _P6_TRANSCRIPTS:
            facts = _extract_facts_from_messages(case["messages"])
            total_facts += len(facts)
            for f in facts:
                if f["type"] in case["expected_types"]:
                    correct_type_facts += 1

        if total_facts > 0:
            precision = correct_type_facts / total_facts
            assert precision >= 0.60, (
                f"Fact type precision {precision:.1%} < 60% "
                f"({correct_type_facts}/{total_facts})"
            )

    def test_heuristic_extraction_pim_skip(self):
        """确认 PIM 工具结果不会被提取为事实。"""
        from butler.core.fact_extraction import _extract_facts_from_messages

        pim_messages = [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "tc_pim", "type": "function",
                 "function": {"name": "memo_add", "arguments": '{"content":"买菜"}'}},
            ]},
            {"role": "tool", "tool_call_id": "tc_pim",
             "content": json.dumps({"ok": True, "id": "m01", "path": "fake.json"})},
        ]
        facts = _extract_facts_from_messages(pim_messages)
        assert len(facts) == 0

    def test_post_session_processor_callable(self):
        """验证 PostSessionProcessor 可以实例化。"""
        _require_smoke()
        from butler.session.post_session import PostSessionProcessor
        processor = PostSessionProcessor()
        assert processor is not None

    def test_post_session_llm_extraction_minimax(self):
        """使用 MiniMax 进行实际 post-session 提取。"""
        from butler.session.post_session import PostSessionProcessor

        client = _make_client("minimax", max_tokens=1024, timeout=120)

        async def llm_call(prompt: str) -> str:
            resp = client.complete(
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content or ""

        processor = PostSessionProcessor()
        processor.set_llm_call(llm_call)

        import asyncio
        result = asyncio.run(processor.process(
            messages=_P6_TRANSCRIPTS[0]["messages"],
            butler_memory=None,
            project_memory=None,
            skill_manager=None,
            project_name="test_project",
        ))

        assert isinstance(result, dict)
        assert not result.get("skipped", False) or result.get("reason") != "error", (
            f"Post-session extraction failed: {result}"
        )

    def test_post_session_llm_extraction_deepseek(self):
        """使用 DeepSeek 进行实际 post-session 提取。"""
        from butler.session.post_session import PostSessionProcessor

        client = _make_client("deepseek", max_tokens=1024, timeout=120)

        async def llm_call(prompt: str) -> str:
            resp = client.complete(
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content or ""

        processor = PostSessionProcessor()
        processor.set_llm_call(llm_call)

        import asyncio
        result = asyncio.run(processor.process(
            messages=_P6_TRANSCRIPTS[3]["messages"],
            butler_memory=None,
            project_memory=None,
            skill_manager=None,
            project_name="test_project",
        ))

        assert isinstance(result, dict)
        assert not result.get("skipped", False) or result.get("reason") != "error", (
            f"Post-session extraction failed: {result}"
        )
