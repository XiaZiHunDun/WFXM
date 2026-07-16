"""L1 Integration Tests — ~150 parameterized tests covering interaction patterns.

These tests validate how ConversationState behaves under different conversation
modes, task complexities, error types, and turn counts. Run on PR.
"""

import pytest

from butler.core.conversation_state import ConversationState


CONVERSATION_MODES = [
    ("feature_development", "功能开发模式"),
    ("bug_fix", "Bug修复模式"),
    ("code_review", "代码审查模式"),
    ("refactoring", "重构模式"),
    ("docs", "文档编写模式"),
    ("testing", "测试开发模式"),
]

TASK_COMPLEXITIES = [
    ("simple", "简单任务"),
    ("medium", "中等任务"),
    ("complex", "复杂任务"),
    ("epic", "史诗任务"),
]

ERROR_TYPES = [
    ("none", "无错误"),
    ("tool_failure", "工具调用失败"),
    ("validation_error", "验证错误"),
    ("timeout", "超时错误"),
    ("rate_limit", "限流错误"),
]

TURN_COUNTS = [5, 10, 15, 20, 25, 30]

FILE_OPERATION_TYPES = [
    ("write", "创建文件"),
    ("patch", "修改文件"),
    ("delete", "删除文件"),
    ("read", "读取文件"),
    ("terminal", "终端命令"),
]

PROJECT_TYPES = [
    ("web_app", "Web应用"),
    ("api_service", "API服务"),
    ("cli_tool", "CLI工具"),
    ("data_pipeline", "数据管道"),
    ("mobile_app", "移动应用"),
    ("ml_model", "机器学习模型"),
]


@pytest.mark.l1
@pytest.mark.parametrize("conversation_mode,mode_desc", CONVERSATION_MODES)
@pytest.mark.parametrize("task_complexity,complexity_desc", TASK_COMPLEXITIES)
class TestConversationPatterns:
    def test_state_tracking_through_turns(
        self,
        conversation_mode: str,
        mode_desc: str,
        task_complexity: str,
        complexity_desc: str,
    ):
        state = ConversationState()
        state.update_conversation_goal(f"{mode_desc}: {complexity_desc}")
        
        for turn in range(1, 11):
            state.add_turn_summary(
                turn_number=turn,
                user_intent=f"第{turn}轮: {mode_desc}任务",
                assistant_action=f"第{turn}轮: 执行{mode_desc}操作",
                result_summary="完成",
                files_touched=[f"{conversation_mode}_{turn}.py"],
            )
        
        assert len(state.turn_summaries) == 10
        assert len(state.files_modified) == 10
        assert f"{mode_desc}: {complexity_desc}" in state.conversation_goal

    def test_decision_tracking_in_mode(
        self,
        conversation_mode: str,
        mode_desc: str,
        task_complexity: str,
        complexity_desc: str,
    ):
        state = ConversationState()
        
        decision_count = {"simple": 1, "medium": 3, "complex": 5, "epic": 8}[task_complexity]
        for i in range(1, decision_count + 1):
            state.add_decision(
                turn_number=i * 2,
                decision=f"{mode_desc}决策{i}",
                rationale=f"{complexity_desc}下的技术选择",
                outcome="已确认" if i % 2 == 0 else "进行中",
            )
        
        assert len(state.decisions_made) == decision_count


@pytest.mark.l1
@pytest.mark.parametrize("error_type,error_desc", ERROR_TYPES)
@pytest.mark.parametrize("turn_count", TURN_COUNTS)
class TestErrorRecoveryPatterns:
    def test_state_stability_after_errors(
        self,
        error_type: str,
        error_desc: str,
        turn_count: int,
    ):
        state = ConversationState()
        state.update_conversation_goal("测试错误恢复")
        
        for turn in range(1, turn_count + 1):
            is_error = error_type != "none" and turn % 3 == 0
            
            if is_error:
                result = f"错误: {error_desc}"
            else:
                result = "成功"
            
            state.add_turn_summary(
                turn_number=turn,
                user_intent=f"第{turn}轮请求",
                assistant_action=f"第{turn}轮操作",
                result_summary=result,
                files_touched=[f"file_{turn}.py"],
            )
            
            if is_error:
                state.add_decision(
                    turn_number=turn,
                    decision=f"处理{error_desc}",
                    rationale=f"第{turn}轮遇到{error_desc}",
                    outcome="已修复",
                )
        
        assert len(state.turn_summaries) == min(turn_count, 20)
        if error_type != "none":
            assert any("错误" in ts.result_summary for ts in state.turn_summaries)

    def test_plan_adjustment_after_errors(
        self,
        error_type: str,
        error_desc: str,
        turn_count: int,
    ):
        state = ConversationState()
        state.add_plan_step("初始计划步骤1")
        state.add_plan_step("初始计划步骤2")
        
        for turn in range(1, turn_count + 1):
            if error_type != "none" and turn % 3 == 0:
                state.add_plan_step(f"修复{error_desc}_轮{turn}")
            else:
                state.add_plan_step(f"正常步骤{turn}")
        
        expected_count = min(2 + turn_count, 20)
        assert len(state.current_plan_steps) == expected_count


@pytest.mark.l1
@pytest.mark.parametrize("file_operation,op_desc", FILE_OPERATION_TYPES)
@pytest.mark.parametrize("project_type,project_desc", PROJECT_TYPES)
class TestFileOperationTracking:
    def test_file_change_logging(
        self,
        file_operation: str,
        op_desc: str,
        project_type: str,
        project_desc: str,
    ):
        state = ConversationState()
        state.update_conversation_goal(f"{project_desc}开发")
        
        for turn in range(1, 6):
            state.add_file_change(
                path=f"{project_type}/module_{turn}.py",
                operation=file_operation,
                description=f"{op_desc}操作",
                turn_number=turn,
            )
        
        assert len(state.file_change_log) == 5
        assert state.file_change_log[0].operation == file_operation
        assert project_type in state.file_change_log[0].path

    def test_files_modified_accumulation(
        self,
        file_operation: str,
        op_desc: str,
        project_type: str,
        project_desc: str,
    ):
        state = ConversationState()
        
        for turn in range(1, 6):
            files = [f"{project_type}/file_{turn}.py", f"{project_type}/file_{turn}_b.py"]
            state.add_turn_summary(
                turn_number=turn,
                user_intent=f"修改文件",
                assistant_action=f"{op_desc}操作",
                result_summary="完成",
                files_touched=files,
            )
        
        assert len(state.files_modified) == 10


@pytest.mark.l1
@pytest.mark.parametrize("turn_count", TURN_COUNTS)
class TestLongConversationIntegration:
    def test_chapter_generation_at_boundaries(self, turn_count: int):
        state = ConversationState()
        
        for turn in range(1, turn_count + 1):
            state.add_turn_summary(
                turn_number=turn,
                user_intent=f"第{turn}轮",
                assistant_action=f"操作{turn}",
                result_summary="完成",
                files_touched=[f"file_{turn}.py"],
            )
        
        expected_chapters = turn_count // 10
        assert len(state.chapter_summaries) <= expected_chapters

    def test_token_budget_with_increasing_content(self, turn_count: int):
        state = ConversationState()
        state.update_conversation_goal("测试Token预算")
        
        for turn in range(1, turn_count + 1):
            state.add_turn_summary(
                turn_number=turn,
                user_intent="X" * 200,
                assistant_action="X" * 200,
                result_summary="完成",
            )
            state.add_decision(turn, "X" * 100, "X" * 200)
            state.add_plan_step("X" * 150)
        
        reminder = state.to_system_reminder(token_budget=1000)
        assert len(reminder) < 4000

    def test_state_invariants_maintained(self, turn_count: int):
        state = ConversationState()
        
        for turn in range(1, turn_count + 1):
            state.add_turn_summary(turn, f"意图{turn}", f"操作{turn}", "完成")
            state.add_decision(turn, f"决策{turn}", "理由")
            state.add_file_change(f"file_{turn}.py", "write", "描述", turn)
        
        assert len(state.turn_summaries) <= 20
        assert len(state.decisions_made) <= 30
        assert len(state.file_change_log) <= 50


@pytest.mark.l1
@pytest.mark.parametrize("project_type,project_desc", PROJECT_TYPES)
@pytest.mark.parametrize("task_complexity,complexity_desc", TASK_COMPLEXITIES)
class TestProjectTypeScenarios:
    def test_task_tree_structure_by_project(
        self,
        project_type: str,
        project_desc: str,
        task_complexity: str,
        complexity_desc: str,
    ):
        state = ConversationState()
        state.update_conversation_goal(f"{project_desc}: {complexity_desc}")
        
        milestone_count = {"simple": 1, "medium": 2, "complex": 3, "epic": 5}[task_complexity]
        
        for m in range(1, milestone_count + 1):
            state.add_task(f"milestone_{m}", f"里程碑{m}")
            for t in range(1, 4):
                state.add_task(
                    f"task_{m}_{t}",
                    f"任务{m}-{t}",
                    parent_id=f"milestone_{m}",
                )
        
        assert state.task_tree is not None
        assert len(state.task_tree.children) == milestone_count

    def test_open_questions_management(
        self,
        project_type: str,
        project_desc: str,
        task_complexity: str,
        complexity_desc: str,
    ):
        state = ConversationState()
        
        question_count = {"simple": 1, "medium": 3, "complex": 5, "epic": 8}[task_complexity]
        
        for i in range(1, question_count + 1):
            state.add_open_question(f"{project_desc}问题{i}")
        
        assert len(state.open_questions) == min(question_count, 15)
        
        for i in range(1, (question_count // 2) + 1):
            state.resolve_open_question(f"{project_desc}问题{i}")
        
        assert len(state.open_questions) == max(0, min(question_count, 15) - (question_count // 2))


@pytest.mark.l1
class TestStatePersistenceIntegration:
    def test_full_state_serialization(self, populated_conversation_state: ConversationState):
        state = populated_conversation_state
        data = state.to_full_state()
        
        assert data["conversation_goal"] == "开发一个电商平台"
        assert data["current_task_summary"] == "完成用户认证模块"
        assert len(data["turn_summaries"]) == 5
        assert len(data["current_plan_steps"]) == 3

    def test_roundtrip_via_full_state(self, populated_conversation_state: ConversationState):
        state = populated_conversation_state
        original_goal = state.conversation_goal
        original_count = len(state.turn_summaries)
        
        data = state.to_full_state()
        
        new_state = ConversationState()
        new_state.update_conversation_goal(data["conversation_goal"])
        new_state.update_task_summary(data["current_task_summary"])
        
        for ts in data["turn_summaries"]:
            new_state.add_turn_summary(
                turn_number=ts["turn_number"],
                user_intent=ts["user_intent"],
                assistant_action=ts["assistant_action"],
                result_summary=ts["result_summary"],
                files_touched=ts.get("files_touched", []),
            )
        
        assert new_state.conversation_goal == original_goal
        assert len(new_state.turn_summaries) == original_count


@pytest.mark.l1
class TestTurnSummarizerIntegration:
    def test_turn_summary_with_all_fields(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        
        for turn in range(1, 11):
            state.add_turn_summary(
                turn_number=turn,
                user_intent=f"用户想要{turn}",
                assistant_action=f"助手做了{turn}",
                result_summary=f"结果{turn}",
                files_touched=[f"file{turn}.py"],
            )
        
        assert len(state.turn_summaries) == 10
        assert all(ts.user_intent for ts in state.turn_summaries)
        assert all(ts.assistant_action for ts in state.turn_summaries)

    def test_file_tracking_cross_turns(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        
        state.add_turn_summary(1, "创建", "创建文件", "完成", ["app.py"])
        state.add_turn_summary(2, "修改", "修改文件", "完成", ["app.py", "utils.py"])
        state.add_turn_summary(3, "创建", "创建文件", "完成", ["models.py"])
        
        assert len(state.files_modified) == 3
        assert "app.py" in state.files_modified
        assert "utils.py" in state.files_modified
        assert "models.py" in state.files_modified
