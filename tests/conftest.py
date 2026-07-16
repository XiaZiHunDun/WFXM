"""Shared fixtures and pytest markers for conversation state tests.

Test Layers:
- L0: Fast unit tests (< 1 second) - run on every commit
- L1: Integration tests (< 60 seconds) - run on PR
- L2: Scenario/property/edge tests (< 5 minutes) - run before merge
- L3: Real LLM end-to-end tests - run on release
"""

import os
import pytest
from typing import Any, List

os.environ["BUTLER_CONVERSATION_STATE_PERSIST"] = "0"

from butler.core.conversation_state import ConversationState


def pytest_configure(config: Any) -> None:
    config.addinivalue_line(
        "markers", "l0: Fast unit tests - run on every commit"
    )
    config.addinivalue_line(
        "markers", "l1: Integration tests - run on PR"
    )
    config.addinivalue_line(
        "markers", "l2: Scenario/property/edge tests - run before merge"
    )
    config.addinivalue_line(
        "markers", "l3: Real LLM end-to-end tests - run on release"
    )


@pytest.fixture
def empty_conversation_state() -> ConversationState:
    return ConversationState()


@pytest.fixture
def populated_conversation_state() -> ConversationState:
    state = ConversationState()
    state.update_conversation_goal("开发一个电商平台")
    state.update_task_summary("完成用户认证模块")
    state.add_plan_step("创建用户模型")
    state.add_plan_step("实现登录接口")
    state.add_plan_step("实现注册接口")
    state.add_open_question("使用JWT还是Session?")
    state.add_decision(1, "使用FastAPI框架", "高性能异步支持", "已确认")
    for i in range(1, 6):
        state.add_turn_summary(
            turn_number=i,
            user_intent=f"第{i}轮用户意图",
            assistant_action=f"第{i}轮助手操作",
            result_summary=f"第{i}轮结果",
            files_touched=[f"file{i}.py"],
        )
    return state


@pytest.fixture
def full_conversation_state() -> ConversationState:
    state = ConversationState()
    state.update_conversation_goal("开发一个复杂的Web应用")
    state.update_task_summary("完成核心功能开发")
    state.current_branch = "feature/auth"
    state.last_build_status = "PASSED"
    state.add_pending_todo("修复登录页面样式")
    state.add_pending_todo("添加单元测试")
    
    for i in range(1, 25):
        state.add_turn_summary(
            turn_number=i,
            user_intent=f"用户意图{i}",
            assistant_action=f"助手操作{i}",
            result_summary=f"结果{i}",
            files_touched=[f"src/{i}.py"],
        )
    
    for i in range(1, 35):
        state.add_decision(i, f"决策{i}", f"理由{i}", f"结果{i}")
    
    for i in range(1, 15):
        state.add_open_question(f"问题{i}")
    
    for i in range(1, 25):
        state.add_plan_step(f"计划步骤{i}")
    
    for i in range(1, 55):
        state.add_file_change(f"file{i}.py", "write", f"描述{i}", i)
    
    for i in range(1, 12):
        state.add_chapter_summary(
            chapter_number=i,
            start_turn=(i-1)*10 + 1,
            end_turn=i*10,
            summary=f"章节{i}摘要",
            key_decisions=[f"决策{i}-1", f"决策{i}-2"],
            key_files=[f"file{i}-1.py", f"file{i}-2.py"],
        )
    
    return state


@pytest.fixture
def mock_tool_call_factory():
    def create_tool_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"name": name, "args": args}
    return create_tool_call


@pytest.fixture
def turn_summary_factory():
    def create_summary(turn_number: int, intent: str, action: str, result: str, files: List[str] = None) -> dict[str, Any]:
        return {
            "turn_number": turn_number,
            "user_intent": intent,
            "assistant_action": action,
            "result_summary": result,
            "files_touched": files or [],
        }
    return create_summary
