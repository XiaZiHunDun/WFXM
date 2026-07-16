"""Complex development workflow tests for multi-turn conversation quality.

This test file validates:
- Task decomposition reasoning chain (complex requirements → TaskTree → sub-task completion)
- Context compression recovery (post-compaction anchor validation)
- 20+ turn end-to-end development flow
- Cross-layer memory coherence (hot/warm/cold layers)
- Error recovery (tool failure, LLM summary failure)
"""

import json
import os
import pytest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from unittest.mock import patch

os.environ["BUTLER_CONVERSATION_STATE_PERSIST"] = "0"

from butler.core.conversation_state import (
    ConversationState,
    TaskNode,
    build_conversation_reminder,
)
from butler.core.turn_summarizer import summarize_turn, summarize_chapter, _extract_file_changes
from butler.core.post_compact_cleanup import _build_conversation_state_anchor


@dataclass
class MockToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    output: str = ""


@dataclass
class MockLLMResponse:
    content: str
    tool_calls: List[MockToolCall] = field(default_factory=list)


class MockAgentLoop:
    """Mock agent loop for multi-turn conversation testing.

    Simulates the complete turn flow:
    user_message → LLM response → tool calls → summarize turn → update state → generate ephemeral system
    """

    def __init__(self, initial_state: ConversationState | None = None):
        self._conversation_state = initial_state or ConversationState()
        self._turn_count = 0
        self._history: List[Dict[str, Any]] = []

    @property
    def conversation_state(self) -> ConversationState:
        return self._conversation_state

    @property
    def turn_count(self) -> int:
        return self._turn_count

    def simulate_turn(
        self,
        user_message: str,
        llm_response: MockLLMResponse,
    ) -> Dict[str, Any]:
        """Simulate one complete turn."""
        self._turn_count += 1

        tool_calls_detail = [
            {"name": tc.name, "args": tc.args, "output": tc.output}
            for tc in llm_response.tool_calls
        ]

        files_touched: List[str] = []
        for tc in tool_calls_detail:
            name = str(tc.get("name", "") or "")
            args = tc.get("args", {}) or {}
            if name in ("read_file", "write_file", "patch", "delete_file"):
                file_path = str(args.get("file_path") or args.get("path") or "")
                if file_path:
                    files_touched.append(file_path)

        file_changes = _extract_file_changes(tool_calls_detail)
        for fc in file_changes:
            if fc["path"]:
                self._conversation_state.add_file_change(
                    path=fc["path"],
                    operation=fc["operation"],
                    description=fc["description"],
                    turn_number=self._turn_count,
                )

        self._auto_detect_branch_and_build_status(tool_calls_detail)

        summary = summarize_turn(
            user_message=user_message,
            assistant_response=llm_response.content,
            tool_calls_detail=tool_calls_detail,
        )

        self._conversation_state.add_turn_summary(
            turn_number=self._turn_count,
            user_intent=summary["user_intent"],
            assistant_action=summary["assistant_action"],
            result_summary=summary["result_summary"],
            files_touched=files_touched,
        )

        if self._turn_count == 1:
            self._conversation_state.update_conversation_goal(user_message[:500])
            self._conversation_state.update_task_summary(user_message[:500])

        self._try_generate_chapter_summary()

        ephemeral_system = build_conversation_reminder(self._conversation_state, token_budget=2000)

        turn_snapshot = {
            "turn_number": self._turn_count,
            "user_message": user_message,
            "llm_response": llm_response.content,
            "tool_calls": [tc.name for tc in llm_response.tool_calls],
            "files_touched": files_touched,
            "ephemeral_system_length": len(ephemeral_system) if ephemeral_system else 0,
            "turn_summaries_count": len(self._conversation_state.turn_summaries),
            "chapter_summaries_count": len(self._conversation_state.chapter_summaries),
            "decisions_count": len(self._conversation_state.decisions_made),
            "files_modified_count": len(self._conversation_state.files_modified),
        }

        self._history.append(turn_snapshot)
        return turn_snapshot

    def _auto_detect_branch_and_build_status(self, tool_calls_detail: List[Dict[str, Any]]) -> None:
        """Auto-detect git branch and build status from mock terminal outputs."""
        import re

        for tc in tool_calls_detail:
            name = str(tc.get("name", "") or "")
            args = tc.get("args", {}) or {}
            cmd = str(args.get("command", "") or "")
            output = str(args.get("output", "") or "")

            if name == "terminal":
                if "git branch" in cmd or "git status" in cmd:
                    match = re.search(r"\* (.*)", output)
                    if match:
                        self._conversation_state.current_branch = match.group(1).strip()[:50]

                if ("pytest" in cmd or "build" in cmd):
                    if "FAILED" in output or "Error" in output:
                        self._conversation_state.last_build_status = "FAILED"
                    elif "passed" in output.lower():
                        self._conversation_state.last_build_status = "PASSED"

    def _try_generate_chapter_summary(self) -> None:
        """Generate chapter summary every 10 turns."""
        if self._turn_count % 10 != 0:
            return

        chapter_number = self._turn_count // 10
        start_turn = (chapter_number - 1) * 10 + 1
        end_turn = self._turn_count

        recent_summaries = [
            {"turn_number": ts.turn_number, "user_intent": ts.user_intent,
             "assistant_action": ts.assistant_action, "result_summary": ts.result_summary,
             "files_touched": ts.files_touched}
            for ts in self._conversation_state.turn_summaries
            if start_turn <= ts.turn_number <= end_turn
        ]

        if not recent_summaries:
            return

        chapter_result = summarize_chapter(recent_summaries)

        self._conversation_state.add_chapter_summary(
            chapter_number=chapter_number,
            start_turn=start_turn,
            end_turn=end_turn,
            summary=chapter_result.get("summary", ""),
            key_decisions=chapter_result.get("key_decisions", []),
            key_files=chapter_result.get("key_files", []),
        )

    def get_history(self) -> List[Dict[str, Any]]:
        return self._history


class TestTaskDecompositionReasoning:
    """Test complex task decomposition into TaskTree and progressive completion."""

    def test_complex_requirement_decomposition(self):
        loop = MockAgentLoop()

        loop.simulate_turn(
            user_message="我需要开发一个电商平台，包含用户认证、商品管理、订单系统和支付集成四大模块",
            llm_response=MockLLMResponse(
                content="好的，我来规划这个电商平台的开发。首先创建项目结构和基础配置。",
                tool_calls=[
                    MockToolCall("write_file", {"file_path": "app.py"}, "文件已创建"),
                    MockToolCall("write_file", {"file_path": "requirements.txt"}, "文件已创建"),
                ],
            ),
        )

        loop.conversation_state.add_task(
            task_id="auth",
            title="用户认证模块",
            status="pending",
            description="登录、注册、JWT认证",
            turn_created=1,
        )
        loop.conversation_state.add_task(
            task_id="products",
            title="商品管理模块",
            status="pending",
            description="商品CRUD、分类、库存",
            turn_created=1,
        )
        loop.conversation_state.add_task(
            task_id="orders",
            title="订单系统",
            status="pending",
            description="创建订单、状态流转、取消",
            turn_created=1,
        )
        loop.conversation_state.add_task(
            task_id="payment",
            title="支付集成",
            status="pending",
            description="微信支付、支付宝、回调",
            turn_created=1,
        )

        assert loop.conversation_state.task_tree is not None
        assert len(loop.conversation_state.task_tree.children) == 4
        task_titles = [t.title for t in loop.conversation_state.task_tree.children]
        assert "用户认证模块" in task_titles
        assert "商品管理模块" in task_titles
        assert "订单系统" in task_titles
        assert "支付集成" in task_titles

    def test_progressive_subtask_completion(self):
        loop = MockAgentLoop()

        loop.conversation_state.add_task(task_id="auth", title="用户认证模块")
        loop.conversation_state.add_task(task_id="login", title="登录API", parent_id="auth")
        loop.conversation_state.add_task(task_id="register", title="注册API", parent_id="auth")
        loop.conversation_state.add_task(task_id="jwt", title="JWT认证", parent_id="auth")

        loop.simulate_turn(
            user_message="实现登录API",
            llm_response=MockLLMResponse(
                content="登录API已实现，包括用户名密码验证和JWT签发",
                tool_calls=[MockToolCall("write_file", {"file_path": "api/login.py"}, "文件已创建")],
            ),
        )
        loop.conversation_state.update_task_status("login", "completed", turn_completed=1)

        loop.simulate_turn(
            user_message="实现注册API",
            llm_response=MockLLMResponse(
                content="注册API已实现，包括密码加密和用户创建",
                tool_calls=[MockToolCall("write_file", {"file_path": "api/register.py"}, "文件已创建")],
            ),
        )
        loop.conversation_state.update_task_status("register", "completed", turn_completed=2)

        assert loop.conversation_state.task_tree is not None
        auth_task = loop.conversation_state.find_task_by_id("auth")
        assert auth_task is not None
        completed_children = [c for c in auth_task.children if c.status == "completed"]
        assert len(completed_children) == 2

        loop.simulate_turn(
            user_message="实现JWT认证中间件",
            llm_response=MockLLMResponse(
                content="JWT认证中间件已实现",
                tool_calls=[MockToolCall("write_file", {"file_path": "middleware/jwt.py"}, "文件已创建")],
            ),
        )
        loop.conversation_state.update_task_status("jwt", "completed", turn_completed=3)
        loop.conversation_state.update_task_status("auth", "completed", turn_completed=3)

        assert loop.conversation_state.find_task_by_id("auth").status == "completed"

    def test_decision_tracking_with_task_progress(self):
        loop = MockAgentLoop()

        loop.simulate_turn(
            user_message="开发用户认证模块，使用什么数据库？",
            llm_response=MockLLMResponse(
                content="建议使用PostgreSQL，支持JSON字段和全文搜索，适合电商场景",
            ),
        )
        loop.conversation_state.add_decision(
            turn_number=1,
            decision="使用PostgreSQL数据库",
            rationale="支持JSON字段和全文搜索，适合电商场景",
            outcome="已确认",
        )

        loop.simulate_turn(
            user_message="好的，开始实现",
            llm_response=MockLLMResponse(
                content="正在创建数据库模型和迁移文件",
                tool_calls=[
                    MockToolCall("write_file", {"file_path": "models/user.py"}, "文件已创建"),
                    MockToolCall("write_file", {"file_path": "alembic/versions/init.py"}, "文件已创建"),
                ],
            ),
        )

        assert len(loop.conversation_state.decisions_made) == 1
        assert "PostgreSQL" in loop.conversation_state.decisions_made[0].decision


class TestContextCompressionRecovery:
    """Test that compressed context preserves all critical information."""

    def test_compact_anchor_contains_all_new_fields(self):
        state = ConversationState()
        state.update_conversation_goal("开发电商平台")
        state.update_task_summary("用户认证模块")
        state.current_branch = "feature/auth"
        state.last_build_status = "PASSED"
        state.add_turn_summary(1, "开始", "创建文件", "完成", ["app.py"])
        state.add_chapter_summary(
            chapter_number=1,
            start_turn=1,
            end_turn=10,
            summary="完成用户认证模块开发",
            key_decisions=["使用PostgreSQL"],
            key_files=["app.py", "models/user.py"],
        )
        state.add_task(task_id="auth", title="用户认证模块")

        anchor = _build_conversation_state_anchor({"conversation_state": state})

        assert "开发电商平台" in anchor
        assert "用户认证模块" in anchor
        assert "feature/auth" in anchor
        assert "PASSED" in anchor

    def test_compact_anchor_from_dict(self):
        state_dict = {
            "conversation_goal": "测试项目",
            "current_task_summary": "测试任务",
            "current_branch": "test-branch",
            "last_build_status": "FAILED",
            "files_modified": ["test.py"],
            "chapter_summaries": [
                {"chapter_number": 1, "start_turn": 1, "end_turn": 10, "summary": "测试章节"}
            ],
        }

        anchor = _build_conversation_state_anchor({"conversation_state": state_dict})

        assert "测试项目" in anchor
        assert "test-branch" in anchor
        assert "FAILED" in anchor
        assert "章节1" in anchor

    def test_ephemeral_system_token_budget_priority(self):
        state = ConversationState()
        state.update_conversation_goal("非常重要的目标")
        state.update_task_summary("非常重要的任务")
        for i in range(30):
            state.add_plan_step(f"不太重要的步骤{i}")
            state.add_decision(i + 1, f"不太重要的决策{i}", "理由")
            state.add_turn_summary(i + 1, f"用户{i}", f"助手{i}", f"结果{i}", [f"file{i}.py"])

        reminder = build_conversation_reminder(state, token_budget=300)

        assert "非常重要的目标" in reminder
        assert "非常重要的任务" in reminder


class TestEndToEndDevelopmentFlow:
    """20+ turn end-to-end development workflow simulation."""

    def test_25_turn_development_cycle(self):
        loop = MockAgentLoop()

        development_plan = [
            {"user": "创建项目结构", "action": "创建基础文件", "files": ["app.py", "requirements.txt"]},
            {"user": "安装依赖", "action": "运行pip install", "terminal": "pip install -r requirements.txt"},
            {"user": "实现用户模型", "action": "创建User模型", "files": ["models/user.py"]},
            {"user": "实现登录API", "action": "创建登录接口", "files": ["api/auth.py"]},
            {"user": "实现注册API", "action": "创建注册接口", "files": ["api/auth.py"]},
            {"user": "实现JWT中间件", "action": "创建认证中间件", "files": ["middleware/jwt.py"]},
            {"user": "实现商品模型", "action": "创建Product模型", "files": ["models/product.py"]},
            {"user": "实现商品CRUD", "action": "创建商品API", "files": ["api/product.py"]},
            {"user": "实现订单模型", "action": "创建Order模型", "files": ["models/order.py"]},
            {"user": "实现订单创建", "action": "创建订单API", "files": ["api/order.py"]},
            {"user": "运行测试", "action": "执行pytest", "terminal": "pytest", "output": "10 passed"},
            {"user": "修复登录bug", "action": "修复密码验证问题", "files": ["api/auth.py"]},
            {"user": "添加商品分类", "action": "创建Category模型", "files": ["models/category.py"]},
            {"user": "实现购物车", "action": "创建Cart模型和API", "files": ["models/cart.py", "api/cart.py"]},
            {"user": "实现支付集成", "action": "创建支付接口", "files": ["api/payment.py"]},
            {"user": "运行完整测试", "action": "执行pytest", "terminal": "pytest", "output": "15 passed"},
            {"user": "重构API路由", "action": "优化路由结构", "files": ["app.py"]},
            {"user": "添加日志", "action": "创建日志配置", "files": ["config/logging.py"]},
            {"user": "添加配置文件", "action": "创建环境配置", "files": ["config/settings.py"]},
            {"user": "部署测试", "action": "运行Gunicorn", "terminal": "gunicorn app:app"},
            {"user": "性能优化", "action": "添加缓存", "files": ["utils/cache.py"]},
            {"user": "安全加固", "action": "添加CORS和安全头", "files": ["middleware/security.py"]},
            {"user": "最终测试", "action": "执行完整测试", "terminal": "pytest", "output": "20 passed"},
            {"user": "总结项目", "action": "项目完成"},
        ]

        for i, step in enumerate(development_plan, 1):
            tool_calls = []
            if step.get("files"):
                for f in step["files"]:
                    tool_calls.append(MockToolCall("write_file", {"file_path": f}, "文件已创建"))
            if step.get("terminal"):
                tool_calls.append(MockToolCall(
                    "terminal",
                    {"command": step["terminal"], "output": step.get("output", "")},
                ))

            snapshot = loop.simulate_turn(
                user_message=f"第{i}步: {step['user']}",
                llm_response=MockLLMResponse(content=f"完成{step['action']}", tool_calls=tool_calls),
            )

            if i == 1:
                assert "创建项目结构" in loop.conversation_state.conversation_goal
            if i == 11:
                assert loop.conversation_state.last_build_status == "PASSED"
            if i == 16:
                assert loop.conversation_state.last_build_status == "PASSED"

        assert loop.turn_count >= 20
        assert len(loop.conversation_state.turn_summaries) == 20
        assert len(loop.conversation_state.chapter_summaries) >= 2
        assert len(loop.conversation_state.files_modified) > 10
        assert loop.conversation_state.last_build_status == "PASSED"

    def test_late_turn_recalls_early_decisions(self):
        loop = MockAgentLoop()

        loop.simulate_turn(
            user_message="创建一个Flask项目，使用SQLAlchemy作为ORM",
            llm_response=MockLLMResponse(
                content="好的，使用Flask + SQLAlchemy技术栈",
                tool_calls=[MockToolCall("write_file", {"file_path": "app.py"}, "文件已创建")],
            ),
        )
        loop.conversation_state.add_decision(
            turn_number=1,
            decision="使用Flask + SQLAlchemy技术栈",
            rationale="轻量级、成熟稳定",
            outcome="已确认",
        )

        for i in range(2, 21):
            loop.simulate_turn(
                user_message=f"第{i}步: 继续开发",
                llm_response=MockLLMResponse(
                    content=f"完成第{i}步开发",
                    tool_calls=[MockToolCall("write_file", {"file_path": f"file{i}.py"}, "文件已创建")],
                ),
            )

        reminder = build_conversation_reminder(loop.conversation_state)
        assert "Flask" in reminder or "SQLAlchemy" in reminder

        decisions = loop.conversation_state.decisions_made
        assert len(decisions) >= 1
        assert any("Flask" in d.decision for d in decisions)


class TestCrossLayerMemoryCoherence:
    """Test coherence across hot/warm/cold memory layers."""

    def test_hot_layer_to_warm_layer_transition(self):
        loop = MockAgentLoop()

        for i in range(1, 11):
            loop.simulate_turn(
                user_message=f"Turn {i}: 开发用户认证功能",
                llm_response=MockLLMResponse(
                    content=f"完成Turn {i}的工作",
                    tool_calls=[MockToolCall("write_file", {"file_path": f"auth{i}.py"}, "文件已创建")],
                ),
            )

        assert len(loop.conversation_state.chapter_summaries) == 1
        chapter = loop.conversation_state.chapter_summaries[0]
        assert chapter.chapter_number == 1
        assert chapter.start_turn == 1
        assert chapter.end_turn == 10

        assert len(chapter.key_files) > 0

    def test_chapter_summary_preserves_key_decisions(self):
        loop = MockAgentLoop()

        loop.simulate_turn(
            user_message="决定使用Redis做缓存",
            llm_response=MockLLMResponse(content="好的，使用Redis缓存"),
        )
        loop.conversation_state.add_decision(
            turn_number=1,
            decision="使用Redis做缓存",
            rationale="提高查询性能",
        )

        for i in range(2, 11):
            loop.simulate_turn(
                user_message=f"Turn {i}: 继续开发",
                llm_response=MockLLMResponse(content=f"完成Turn {i}"),
            )

        assert len(loop.conversation_state.chapter_summaries) == 1
        chapter = loop.conversation_state.chapter_summaries[0]
        assert "Redis" in chapter.summary or "缓存" in chapter.summary

    def test_keyword_search_across_turns_and_chapters(self):
        from butler.tools.conversation_state_tools import persist_conversation_state, load_conversation_state

        state = ConversationState()
        state.add_turn_summary(1, "创建用户模型", "创建User类", "完成", ["models/user.py"])
        state.add_turn_summary(2, "创建商品模型", "创建Product类", "完成", ["models/product.py"])
        state.add_turn_summary(3, "创建订单模型", "创建Order类", "完成", ["models/order.py"])
        state.add_chapter_summary(
            chapter_number=1,
            start_turn=1,
            end_turn=3,
            summary="完成数据模型开发，包括用户、商品、订单",
            key_files=["models/user.py", "models/product.py", "models/order.py"],
        )

        persist_conversation_state(state)

        from butler.tools.conversation_state_tools import tool_conversation_state_search

        result = tool_conversation_state_search("用户")
        data = json.loads(result)
        assert data["ok"] is True
        assert len(data["results"]) >= 1

        result = tool_conversation_state_search("订单")
        data = json.loads(result)
        assert data["ok"] is True
        assert len(data["results"]) >= 1


class TestErrorRecovery:
    """Test that errors don't corrupt conversation state."""

    def test_tool_execution_failure(self):
        loop = MockAgentLoop()

        loop.simulate_turn(
            user_message="读取一个不存在的文件",
            llm_response=MockLLMResponse(
                content="文件不存在，继续尝试其他操作",
                tool_calls=[MockToolCall("read_file", {"file_path": "nonexistent.py"}, "FileNotFoundError")],
            ),
        )

        assert loop.turn_count == 1
        assert len(loop.conversation_state.turn_summaries) == 1
        assert loop.conversation_state.is_empty is False

        loop.simulate_turn(
            user_message="创建正确的文件",
            llm_response=MockLLMResponse(
                content="文件已创建",
                tool_calls=[MockToolCall("write_file", {"file_path": "correct.py"}, "文件已创建")],
            ),
        )

        assert loop.turn_count == 2
        assert "correct.py" in loop.conversation_state.files_modified

    def test_llm_summary_fallback(self):
        loop = MockAgentLoop()

        with patch("butler.core.turn_summarizer._get_summarizer_config", return_value=("", "", "")):
            loop.simulate_turn(
                user_message="创建一个复杂的文件",
                llm_response=MockLLMResponse(
                    content="已创建复杂文件",
                    tool_calls=[MockToolCall("write_file", {"file_path": "complex.py"}, "文件已创建")],
                ),
            )

        assert loop.turn_count == 1
        assert len(loop.conversation_state.turn_summaries) == 1
        assert "complex.py" in loop.conversation_state.files_modified

    def test_state_reset(self):
        loop = MockAgentLoop()

        loop.simulate_turn(
            user_message="创建文件",
            llm_response=MockLLMResponse(
                content="文件已创建",
                tool_calls=[MockToolCall("write_file", {"file_path": "test.py"}, "文件已创建")],
            ),
        )
        loop.conversation_state.add_decision(1, "测试决策", "理由")
        loop.conversation_state.add_task(task_id="test", title="测试任务")

        assert loop.conversation_state.is_empty is False
        assert len(loop.conversation_state.files_modified) == 1

        loop.conversation_state.reset()

        assert loop.conversation_state.is_empty is True
        assert loop.conversation_state.task_tree is None