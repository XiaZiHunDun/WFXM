"""L3 Multi-Scenario Long Conversation Tests — Real LLM tests for various project types.

Covers:
- Project types: Agent Development, Web App, API Service, CLI Tool, Data Pipeline
- Turn counts: 10, 20, 50, 100
- Memory management across different conversation lengths
"""

import os
import time
import pytest

from butler.core.conversation_state import ConversationState
from butler.core.turn_summarizer import summarize_turn, summarize_chapter


PROJECT_TYPES = [
    ("agent", "Agent智能助手开发", 6),
    ("web", "Web前端应用开发", 5),
    ("api", "RESTful API服务", 6),
    ("cli", "CLI命令行工具", 4),
    ("data", "数据处理管道", 5),
]

TURN_COUNTS = [10, 20, 50, 100]


class ProjectScenarioGenerator:
    @staticmethod
    def generate_agent_scenario(turn_count: int) -> list[dict]:
        phases = [
            ("项目初始化", 3),
            ("工具注册", 3),
            ("对话循环", 3),
            ("记忆管理", 3),
            ("测试部署", 3),
        ]
        intents = {
            "项目初始化": [
                "创建Agent项目结构",
                "配置依赖和环境",
                "创建主入口文件",
            ],
            "工具注册": [
                "创建工具注册机制",
                "实现基础工具（搜索、文件操作）",
                "添加工具调用逻辑",
            ],
            "对话循环": [
                "实现Agent对话循环",
                "集成LLM客户端",
                "添加响应生成逻辑",
            ],
            "记忆管理": [
                "实现短期记忆存储",
                "添加长期记忆检索",
                "实现记忆压缩策略",
            ],
            "测试部署": [
                "编写单元测试",
                "添加配置管理",
                "创建部署脚本",
            ],
        }
        actions = {
            "项目初始化": ["创建目录结构", "配置requirements.txt", "创建main.py"],
            "工具注册": ["创建tool_registry.py", "实现search_tool", "实现file_tool"],
            "对话循环": ["实现agent_loop.py", "集成OpenAI", "添加response_generator"],
            "记忆管理": ["实现short_term_memory", "集成vector_store", "实现memory_compressor"],
            "测试部署": ["编写test_agent.py", "创建config.py", "创建deploy.sh"],
        }
        return ProjectScenarioGenerator._build_scenario(turn_count, phases, intents, actions)

    @staticmethod
    def generate_web_scenario(turn_count: int) -> list[dict]:
        phases = [
            ("项目初始化", 2),
            ("UI组件", 4),
            ("状态管理", 3),
            ("API集成", 3),
            ("部署优化", 3),
        ]
        intents = {
            "项目初始化": ["初始化React/Vue项目", "配置构建工具"],
            "UI组件": ["创建布局组件", "实现表单组件", "创建列表组件", "实现模态框"],
            "状态管理": ["配置状态管理", "实现数据持久化", "添加缓存策略"],
            "API集成": ["配置API客户端", "实现认证接口", "添加数据获取"],
            "部署优化": ["代码分割优化", "添加CI/CD", "配置生产环境"],
        }
        actions = {
            "项目初始化": ["npm create vite", "配置tailwindcss"],
            "UI组件": ["创建Layout.tsx", "实现Form.tsx", "创建List.tsx", "实现Modal.tsx"],
            "状态管理": ["配置zustand", "实现localStorage", "添加SWR"],
            "API集成": ["创建api/client.ts", "实现auth.ts", "添加data/fetchers"],
            "部署优化": ["配置code splitting", "创建GitHub Actions", "配置nginx"],
        }
        return ProjectScenarioGenerator._build_scenario(turn_count, phases, intents, actions)

    @staticmethod
    def generate_api_scenario(turn_count: int) -> list[dict]:
        phases = [
            ("项目初始化", 2),
            ("数据库设计", 3),
            ("API开发", 5),
            ("认证授权", 3),
            ("测试部署", 3),
        ]
        intents = {
            "项目初始化": ["初始化FastAPI项目", "配置依赖"],
            "数据库设计": ["设计数据模型", "配置ORM", "创建迁移脚本"],
            "API开发": ["实现CRUD接口", "添加分页排序", "实现批量操作", "添加导出功能", "实现Webhook"],
            "认证授权": ["实现OAuth2认证", "添加角色权限", "配置API密钥"],
            "测试部署": ["编写集成测试", "配置Docker", "设置监控告警"],
        }
        actions = {
            "项目初始化": ["创建main.py", "配置requirements.txt"],
            "数据库设计": ["创建models.py", "配置SQLAlchemy", "编写alembic迁移"],
            "API开发": ["实现CRUD", "添加pagination", "实现batch", "添加export", "实现webhook"],
            "认证授权": ["实现OAuth2", "添加RBAC", "配置API key"],
            "测试部署": ["编写test_api.py", "创建Dockerfile", "配置prometheus"],
        }
        return ProjectScenarioGenerator._build_scenario(turn_count, phases, intents, actions)

    @staticmethod
    def generate_cli_scenario(turn_count: int) -> list[dict]:
        phases = [
            ("项目初始化", 2),
            ("命令实现", 4),
            ("参数解析", 2),
            ("测试发布", 3),
        ]
        intents = {
            "项目初始化": ["创建CLI项目", "配置setup.py"],
            "命令实现": ["实现主命令", "添加子命令", "实现参数处理", "添加输出格式化"],
            "参数解析": ["配置argparse", "添加配置文件支持"],
            "测试发布": ["编写单元测试", "配置CI/CD", "发布到PyPI"],
        }
        actions = {
            "项目初始化": ["创建cli.py", "配置setup.py"],
            "命令实现": ["实现main_cmd", "添加sub_cmd", "实现arg_handler", "添加output_formatter"],
            "参数解析": ["配置argparse", "添加yaml支持"],
            "测试发布": ["编写test_cli.py", "创建GitHub Actions", "配置twine"],
        }
        return ProjectScenarioGenerator._build_scenario(turn_count, phases, intents, actions)

    @staticmethod
    def generate_data_scenario(turn_count: int) -> list[dict]:
        phases = [
            ("项目初始化", 2),
            ("数据采集", 3),
            ("数据处理", 4),
            ("数据存储", 3),
            ("调度监控", 3),
        ]
        intents = {
            "项目初始化": ["创建数据项目", "配置环境"],
            "数据采集": ["实现API采集", "添加爬虫", "实现消息队列消费"],
            "数据处理": ["数据清洗", "数据转换", "特征工程", "数据验证"],
            "数据存储": ["配置数据库", "实现数据写入", "添加索引优化"],
            "调度监控": ["配置Airflow调度", "添加日志监控", "设置告警通知"],
        }
        actions = {
            "项目初始化": ["创建project目录", "配置pyproject.toml"],
            "数据采集": ["实现api_fetcher", "添加scraper", "实现kafka_consumer"],
            "数据处理": ["实现cleaner", "实现transformer", "实现feature_engineer", "添加validator"],
            "数据存储": ["配置postgres", "实现writer", "添加indexes"],
            "调度监控": ["配置airflow", "添加logging", "配置alerting"],
        }
        return ProjectScenarioGenerator._build_scenario(turn_count, phases, intents, actions)

    @staticmethod
    def _build_scenario(turn_count: int, phases: list, intents: dict, actions: dict) -> list[dict]:
        scenario = []
        phase_index = 0
        step_index = 0
        
        for turn in range(1, turn_count + 1):
            phase_name, phase_length = phases[phase_index % len(phases)]
            phase_intents = intents.get(phase_name, [])
            phase_actions = actions.get(phase_name, [])
            
            intent_idx = step_index % len(phase_intents) if phase_intents else 0
            action_idx = step_index % len(phase_actions) if phase_actions else 0
            
            scenario.append({
                "turn": turn,
                "phase": phase_name,
                "user_intent": phase_intents[intent_idx] if phase_intents else f"第{turn}轮：继续开发",
                "assistant_action": phase_actions[action_idx] if phase_actions else "执行开发操作",
                "tool_calls": [{"name": "write_file", "args": {"file_path": f"{phase_name}/{turn}.py"}}],
            })
            
            step_index += 1
            if step_index >= phase_length:
                step_index = 0
                phase_index += 1
        
        return scenario


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
@pytest.mark.parametrize("project_type,project_name,expected_chapters", PROJECT_TYPES)
@pytest.mark.parametrize("turn_count", TURN_COUNTS)
class TestMultiScenarioLongConversation:
    def test_long_conversation_by_scenario(self, project_type: str, project_name: str, expected_chapters: int, turn_count: int):
        print(f"\n=== 测试: {project_name} ({turn_count}轮) ===")
        
        state = ConversationState()
        state.update_conversation_goal(project_name)
        
        scenario_generator = {
            "agent": ProjectScenarioGenerator.generate_agent_scenario,
            "web": ProjectScenarioGenerator.generate_web_scenario,
            "api": ProjectScenarioGenerator.generate_api_scenario,
            "cli": ProjectScenarioGenerator.generate_cli_scenario,
            "data": ProjectScenarioGenerator.generate_data_scenario,
        }
        
        scenario = scenario_generator[project_type](turn_count)
        all_summaries = []
        
        start_time = time.time()
        
        for item in scenario:
            summary = summarize_turn(
                user_message=item["user_intent"],
                assistant_response="我来帮你完成这个任务。",
                tool_calls_detail=item["tool_calls"],
            )
            
            state.add_turn_summary(
                turn_number=item["turn"],
                user_intent=summary["user_intent"],
                assistant_action=summary["assistant_action"],
                result_summary=summary["result_summary"],
                files_touched=[tc["args"].get("file_path", "") for tc in item["tool_calls"]],
            )
            
            all_summaries.append({
                "turn_number": item["turn"],
                "user_intent": summary["user_intent"],
                "assistant_action": summary["assistant_action"],
                "result_summary": summary["result_summary"],
                "files_touched": [tc["args"].get("file_path", "") for tc in item["tool_calls"]],
            })
            
            if item["turn"] % 10 == 0:
                chapter_summary = summarize_chapter(all_summaries[-10:])
                state.add_chapter_summary(
                    chapter_number=item["turn"] // 10,
                    start_turn=item["turn"] - 9,
                    end_turn=item["turn"],
                    summary=chapter_summary["summary"],
                    key_decisions=chapter_summary.get("key_decisions", []),
                    key_files=chapter_summary.get("key_files", []),
                    key_technologies=chapter_summary.get("key_technologies", []),
                )
        
        elapsed = time.time() - start_time
        
        assert len(state.turn_summaries) == min(turn_count, state._max_turn_summaries)
        assert len(state.chapter_summaries) == turn_count // 10
        
        reminder = state.to_system_reminder()
        assert len(reminder) > 50
        
        print(f"  耗时: {elapsed:.1f}秒")
        print(f"  平均每轮: {elapsed/turn_count:.2f}秒")
        print(f"  系统提醒长度: {len(reminder)}字符")
        print(f"  章节摘要数量: {len(state.chapter_summaries)}")
        print(f"  文件修改数量: {len(state.files_modified)}")


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class TestMemoryRetentionAcrossTurns:
    def test_memory_retention_10_turns(self):
        self._test_memory_retention(10)

    def test_memory_retention_20_turns(self):
        self._test_memory_retention(20)

    def test_memory_retention_50_turns(self):
        self._test_memory_retention(50)

    def test_memory_retention_100_turns(self):
        self._test_memory_retention(100)

    def _test_memory_retention(self, turn_count: int):
        state = ConversationState()
        state.update_conversation_goal("开发复杂系统")
        
        key_points = []
        all_summaries = []
        
        for i in range(1, turn_count + 1):
            if i in [1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]:
                tech_stack = ["FastAPI", "PostgreSQL", "Redis", "JWT", "WebSocket", "Celery", "Docker", "Kubernetes", "Prometheus", "Grafana", "ELK"][i // 5 % 11]
                user_msg = f"集成{tech_stack}到项目中"
                key_points.append(tech_stack)
            else:
                user_msg = f"第{i}轮：继续开发"
            
            summary = summarize_turn(user_msg, "执行开发操作", [])
            state.add_turn_summary(i, summary["user_intent"], summary["assistant_action"], summary["result_summary"])
            
            all_summaries.append({
                "turn_number": i,
                "user_intent": summary["user_intent"],
                "assistant_action": summary["assistant_action"],
                "result_summary": summary["result_summary"],
                "files_touched": [],
            })
            
            if i % 10 == 0:
                chapter_summary = summarize_chapter(all_summaries[-10:])
                state.add_chapter_summary(
                    chapter_number=i // 10,
                    start_turn=i - 9,
                    end_turn=i,
                    summary=chapter_summary["summary"],
                    key_decisions=chapter_summary.get("key_decisions", []),
                    key_files=chapter_summary.get("key_files", []),
                    key_technologies=chapter_summary.get("key_technologies", []),
                )
        
        reminder = state.to_system_reminder()
        matched_points = [point for point in key_points if point in reminder]
        recall_rate = len(matched_points) / len(key_points)
        
        print(f"\n=== 记忆保留测试 ({turn_count}轮) ===")
        print(f"关键技术点: {key_points}")
        print(f"成功召回: {matched_points}")
        print(f"召回率: {recall_rate:.1%}")
        
        expected_recall = 0.9 if turn_count <= 20 else 0.5
        assert recall_rate >= expected_recall, f"记忆召回率不足: {recall_rate:.1%} (期望 >= {expected_recall:.0%})"


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class TestAgentSpecificScenario:
    def test_agent_development_50_turns(self):
        state = ConversationState()
        state.update_conversation_goal("开发一个智能Agent系统")
        
        agent_phases = [
            ("架构设计", ["设计Agent架构", "定义Agent角色", "规划工具集"]),
            ("核心循环", ["实现思考循环", "实现工具调用", "实现响应生成"]),
            ("记忆系统", ["实现短期记忆", "实现长期记忆", "实现记忆检索"]),
            ("学习能力", ["实现经验学习", "实现技能获取", "实现自我改进"]),
            ("评估部署", ["编写评估测试", "配置部署环境", "设置监控告警"]),
        ]
        
        turn_count = 1
        all_summaries = []
        
        start_time = time.time()
        
        for phase_name, phase_tasks in agent_phases:
            for task in phase_tasks:
                for sub_step in range(3):
                    if turn_count > 50:
                        break
                    
                    sub_task = f"{task} - 第{sub_step + 1}步" if sub_step > 0 else task
                    summary = summarize_turn(
                        user_message=sub_task,
                        assistant_response="我来帮你实现这个功能。",
                        tool_calls_detail=[
                            {"name": "write_file", "args": {"file_path": f"agent/{phase_name}/{turn_count}.py"}}
                        ],
                    )
                    
                    state.add_turn_summary(
                        turn_number=turn_count,
                        user_intent=summary["user_intent"],
                        assistant_action=summary["assistant_action"],
                        result_summary=summary["result_summary"],
                        files_touched=[f"agent/{phase_name}/{turn_count}.py"],
                    )
                    
                    all_summaries.append({
                        "turn_number": turn_count,
                        "user_intent": summary["user_intent"],
                        "assistant_action": summary["assistant_action"],
                        "result_summary": summary["result_summary"],
                        "files_touched": [f"agent/{phase_name}/{turn_count}.py"],
                    })
                    
                    if turn_count % 10 == 0:
                        chapter_summary = summarize_chapter(all_summaries[-10:])
                        state.add_chapter_summary(
                            chapter_number=turn_count // 10,
                            start_turn=turn_count - 9,
                            end_turn=turn_count,
                            summary=chapter_summary["summary"],
                            key_decisions=chapter_summary.get("key_decisions", []),
                            key_files=chapter_summary.get("key_files", []),
                            key_technologies=chapter_summary.get("key_technologies", []),
                        )
                    
                    turn_count += 1
        
        elapsed = time.time() - start_time
        
        reminder = state.to_system_reminder()
        
        agent_keywords = ["Agent", "思考", "工具", "记忆", "学习"]
        matched_keywords = [kw for kw in agent_keywords if kw in reminder]
        
        print(f"\n=== Agent开发测试 (50轮) ===")
        print(f"耗时: {elapsed:.1f}秒")
        print(f"系统提醒长度: {len(reminder)}字符")
        print(f"章节摘要数量: {len(state.chapter_summaries)}")
        print(f"匹配关键词: {matched_keywords}")
        
        assert len(matched_keywords) >= 3, f"Agent相关关键词匹配不足: {matched_keywords}"
