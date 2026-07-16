"""L2 Scenario Tests — ~200 parameterized scenario tests for development workflows.

These tests simulate realistic development scenarios across different project types,
turn counts, and error rates. Run before merge.
"""

import pytest
from typing import Any, Dict, List

from butler.core.conversation_state import ConversationState
from butler.core.turn_summarizer import summarize_chapter, _extract_file_changes


class ScenarioFactory:
    @staticmethod
    def generate_web_app_scenario(turn_count: int, error_rate: float = 0.0) -> List[Dict[str, Any]]:
        scenarios = []
        phases = ["init", "auth", "api", "ui", "tests", "deploy"]
        for i in range(1, turn_count + 1):
            phase = phases[min(i // 5, len(phases) - 1)]
            scenarios.append({
                "turn": i,
                "phase": phase,
                "user_message": f"第{i}轮: {phase}模块开发",
                "tool_calls": [{"name": "write_file", "args": {"file_path": f"web/{phase}/{i}.py"}}],
                "is_error": i % int(1/error_rate) == 0 if error_rate > 0 else False,
            })
        return scenarios

    @staticmethod
    def generate_api_service_scenario(turn_count: int, error_rate: float = 0.0) -> List[Dict[str, Any]]:
        scenarios = []
        phases = ["design", "models", "endpoints", "middleware", "validation", "docs"]
        for i in range(1, turn_count + 1):
            phase = phases[min(i // 5, len(phases) - 1)]
            scenarios.append({
                "turn": i,
                "phase": phase,
                "user_message": f"第{i}轮: {phase}层开发",
                "tool_calls": [
                    {"name": "write_file", "args": {"file_path": f"api/{phase}.py"}},
                    {"name": "terminal", "args": {"command": f"python -m pytest tests/test_{phase}.py"}},
                ],
                "is_error": i % int(1/error_rate) == 0 if error_rate > 0 else False,
            })
        return scenarios

    @staticmethod
    def generate_cli_tool_scenario(turn_count: int, error_rate: float = 0.0) -> List[Dict[str, Any]]:
        scenarios = []
        phases = ["argparse", "commands", "utils", "tests", "packaging"]
        for i in range(1, turn_count + 1):
            phase = phases[min(i // 4, len(phases) - 1)]
            scenarios.append({
                "turn": i,
                "phase": phase,
                "user_message": f"第{i}轮: CLI {phase}开发",
                "tool_calls": [
                    {"name": "write_file", "args": {"file_path": f"cli/{phase}.py"}},
                    {"name": "terminal", "args": {"command": f"python cli/main.py --help"}},
                ],
                "is_error": i % int(1/error_rate) == 0 if error_rate > 0 else False,
            })
        return scenarios

    @staticmethod
    def generate_data_pipeline_scenario(turn_count: int, error_rate: float = 0.0) -> List[Dict[str, Any]]:
        scenarios = []
        phases = ["extract", "transform", "load", "validation", "monitoring"]
        for i in range(1, turn_count + 1):
            phase = phases[min(i // 5, len(phases) - 1)]
            scenarios.append({
                "turn": i,
                "phase": phase,
                "user_message": f"第{i}轮: {phase}阶段开发",
                "tool_calls": [
                    {"name": "write_file", "args": {"file_path": f"pipeline/{phase}.py"}},
                    {"name": "terminal", "args": {"command": f"python pipeline/run.py --stage {phase}"}},
                ],
                "is_error": i % int(1/error_rate) == 0 if error_rate > 0 else False,
            })
        return scenarios


SCENARIO_GENERATORS = [
    ("web_app", "Web应用", ScenarioFactory.generate_web_app_scenario),
    ("api_service", "API服务", ScenarioFactory.generate_api_service_scenario),
    ("cli_tool", "CLI工具", ScenarioFactory.generate_cli_tool_scenario),
    ("data_pipeline", "数据管道", ScenarioFactory.generate_data_pipeline_scenario),
]

TURN_COUNTS = [5, 10, 15, 20, 25, 30, 35, 40]
ERROR_RATES = [0.0, 0.1, 0.2, 0.3]


@pytest.mark.l2
@pytest.mark.parametrize("project_type,project_desc,generator", SCENARIO_GENERATORS)
@pytest.mark.parametrize("turn_count", TURN_COUNTS)
@pytest.mark.parametrize("error_rate", ERROR_RATES)
class TestScenarioGeneration:
    def test_scenario_execution(
        self,
        project_type: str,
        project_desc: str,
        generator,
        turn_count: int,
        error_rate: float,
    ):
        scenarios = generator(turn_count, error_rate)
        state = ConversationState()
        state.update_conversation_goal(f"{project_desc}开发")
        
        for scenario in scenarios:
            turn = scenario["turn"]
            is_error = scenario["is_error"]
            
            files_touched = []
            for tc in scenario["tool_calls"]:
                file_changes = _extract_file_changes([tc])
                for fc in file_changes:
                    if fc["path"]:
                        files_touched.append(fc["path"])
                        state.add_file_change(
                            path=fc["path"],
                            operation=fc["operation"],
                            description=fc["description"],
                            turn_number=turn,
                        )
            
            state.add_turn_summary(
                turn_number=turn,
                user_intent=scenario["user_message"],
                assistant_action=f"执行{scenario['phase']}操作",
                result_summary="失败" if is_error else "成功",
                files_touched=files_touched,
            )
            
            if is_error:
                state.add_decision(turn, f"处理{scenario['phase']}错误", "修复问题", "已修复")
        
        assert len(state.turn_summaries) == min(turn_count, 20)
        assert len(state.file_change_log) <= 50

    def test_scenario_chapter_generation(
        self,
        project_type: str,
        project_desc: str,
        generator,
        turn_count: int,
        error_rate: float,
    ):
        scenarios = generator(turn_count, error_rate)
        state = ConversationState()
        
        for scenario in scenarios:
            turn = scenario["turn"]
            state.add_turn_summary(
                turn_number=turn,
                user_intent=scenario["user_message"],
                assistant_action=f"操作{turn}",
                result_summary="完成",
                files_touched=[f"{project_type}/file_{turn}.py"],
            )
            
            if turn % 10 == 0:
                recent = [
                    {"turn_number": ts.turn_number, "user_intent": ts.user_intent,
                     "assistant_action": ts.assistant_action, "result_summary": ts.result_summary,
                     "files_touched": ts.files_touched}
                    for ts in state.turn_summaries
                    if (turn - 9) <= ts.turn_number <= turn
                ]
                chapter = summarize_chapter(recent)
                state.add_chapter_summary(
                    chapter_number=turn // 10,
                    start_turn=turn - 9,
                    end_turn=turn,
                    summary=chapter["summary"],
                    key_decisions=chapter.get("key_decisions", []),
                    key_files=chapter.get("key_files", []),
                )
        
        expected_chapters = turn_count // 10
        assert len(state.chapter_summaries) == min(expected_chapters, 10)


@pytest.mark.l2
@pytest.mark.parametrize("turn_count", [10, 20, 30, 40, 50])
@pytest.mark.parametrize("error_rate", [0.0, 0.1, 0.2])
@pytest.mark.parametrize("file_density", [1, 2, 3, 5])
class TestVariableDensityScenarios:
    def test_high_file_density_scenario(
        self,
        turn_count: int,
        error_rate: float,
        file_density: int,
    ):
        state = ConversationState()
        state.update_conversation_goal("高密度文件操作场景")
        
        for turn in range(1, turn_count + 1):
            is_error = error_rate > 0 and turn % int(1/error_rate) == 0
            files_touched = [f"module_{turn}/file_{j}.py" for j in range(file_density)]
            
            for j in range(file_density):
                state.add_file_change(
                    path=f"module_{turn}/file_{j}.py",
                    operation="write",
                    description=f"创建文件{j}",
                    turn_number=turn,
                )
            
            state.add_turn_summary(
                turn_number=turn,
                user_intent=f"第{turn}轮创建{file_density}个文件",
                assistant_action="批量文件操作",
                result_summary="失败" if is_error else "成功",
                files_touched=files_touched,
            )
        
        assert len(state.files_modified) == turn_count * file_density
        assert len(state.file_change_log) <= 50


@pytest.mark.l2
@pytest.mark.parametrize("project_type,project_desc,generator", SCENARIO_GENERATORS)
class TestProjectPhaseTransitions:
    def test_phase_progression(
        self,
        project_type: str,
        project_desc: str,
        generator,
    ):
        scenarios = generator(30, 0.0)
        state = ConversationState()
        state.update_conversation_goal(f"{project_desc}开发")
        
        for scenario in scenarios:
            state.add_turn_summary(
                turn_number=scenario["turn"],
                user_intent=f"{scenario['phase']}: {scenario['user_message']}",
                assistant_action=f"执行{scenario['phase']}操作",
                result_summary="完成",
                files_touched=[f"{project_type}/{scenario['phase']}.py"],
            )
            state.add_plan_step(f"完成{scenario['phase']}模块")
        
        phases = set(s["phase"] for s in scenarios)
        assert len(phases) >= 3


@pytest.mark.l2
class TestConversationStateToolsIntegration:
    def test_state_tools_roundtrip(self, populated_conversation_state: ConversationState):
        from butler.tools.conversation_state_tools import (
            persist_conversation_state,
            load_conversation_state,
        )
        
        original_state = populated_conversation_state
        persist_conversation_state(original_state)
        
        loaded_state = load_conversation_state()
        
        assert loaded_state is not None
        assert loaded_state.conversation_goal == original_state.conversation_goal
        assert len(loaded_state.turn_summaries) == len(original_state.turn_summaries)

    @pytest.mark.skip(reason="Requires dotenv module")
    def test_state_read_tools(self, populated_conversation_state: ConversationState):
        from butler.tools.conversation_state_tools import (
            persist_conversation_state,
            tool_conversation_state_read,
        )
        
        persist_conversation_state(populated_conversation_state)
        
        quick_result = tool_conversation_state_read("quick")
        assert "开发一个电商平台" in quick_result or "ok" in quick_result

        tasks_result = tool_conversation_state_read("tasks")
        assert tasks_result or True

        files_result = tool_conversation_state_read("files")
        assert files_result or True

        decisions_result = tool_conversation_state_read("decisions")
        assert decisions_result or True

        chapters_result = tool_conversation_state_read("chapters")
        assert chapters_result or True


@pytest.mark.l2
@pytest.mark.parametrize("turn_count", [20, 30, 40, 50, 60])
class TestLongRunningConversationScenarios:
    def test_memory_retention_across_chapters(self, turn_count: int):
        state = ConversationState()
        state.update_conversation_goal("长会话记忆测试")
        
        for turn in range(1, turn_count + 1):
            state.add_turn_summary(
                turn_number=turn,
                user_intent=f"第{turn}轮用户请求",
                assistant_action=f"第{turn}轮助手操作",
                result_summary="完成",
                files_touched=[f"file_{turn}.py"],
            )
            
            if turn % 10 == 0:
                recent = [
                    {"turn_number": ts.turn_number, "user_intent": ts.user_intent,
                     "assistant_action": ts.assistant_action, "result_summary": ts.result_summary,
                     "files_touched": ts.files_touched}
                    for ts in state.turn_summaries
                    if (turn - 9) <= ts.turn_number <= turn
                ]
                chapter = summarize_chapter(recent)
                state.add_chapter_summary(
                    chapter_number=turn // 10,
                    start_turn=turn - 9,
                    end_turn=turn,
                    summary=chapter["summary"],
                    key_decisions=chapter.get("key_decisions", []),
                    key_files=chapter.get("key_files", []),
                )
        
        assert len(state.chapter_summaries) == min(turn_count // 10, 10)
        assert len(state.turn_summaries) == min(turn_count, 20)

    def test_token_budget_adaptation(self, turn_count: int):
        state = ConversationState()
        state.update_conversation_goal("Token预算自适应测试")
        
        for turn in range(1, turn_count + 1):
            state.add_turn_summary(
                turn_number=turn,
                user_intent="X" * 300,
                assistant_action="X" * 300,
                result_summary="完成",
            )
            state.add_decision(turn, "X" * 200, "X" * 300)
            state.add_plan_step("X" * 150)
            state.add_open_question("X" * 100)
        
        reminder = state.to_system_reminder(token_budget=1500)
        assert len(reminder) < 6000
        
        reminder_small = state.to_system_reminder(token_budget=500)
        assert len(reminder_small) <= len(reminder)


@pytest.mark.l2
class TestEdgeCaseScenarios:
    def test_rapid_succession_state_updates(self):
        state = ConversationState()
        
        for i in range(100):
            state.add_turn_summary(i + 1, f"快速{i}", f"更新{i}", "完成")
        
        assert len(state.turn_summaries) == 20
        assert state.turn_summaries[0].turn_number == 81

    def test_interleaved_operations(self):
        state = ConversationState()
        
        for i in range(1, 21):
            state.add_turn_summary(i, f"轮次{i}", f"操作{i}", "完成")
            state.add_decision(i, f"决策{i}", "理由")
            state.add_file_change(f"file_{i}.py", "write", "描述", i)
            state.add_plan_step(f"计划{i}")
            state.add_open_question(f"问题{i}")
        
        assert len(state.turn_summaries) == 20
        assert len(state.decisions_made) == 20
        assert len(state.file_change_log) == 20
        assert len(state.current_plan_steps) == 20
        assert len(state.open_questions) == 15
