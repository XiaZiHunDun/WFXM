"""L3 Long Conversation Test — 50-turn real LLM conversation simulation.

This test simulates a complete project development workflow across 50 turns,
validating memory management, task tracking, and context preservation.

Requires: DEEPSEEK_API_KEY or MINIMAX_API_KEY
"""

import os
import time
import pytest

from butler.core.conversation_state import ConversationState
from butler.core.turn_summarizer import summarize_turn, summarize_chapter


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class Test50TurnLongConversation:
    def test_50_turn_ecommerce_project(self):
        state = ConversationState()
        state.update_conversation_goal("开发一个电商平台后端API")
        
        phases = [
            ("项目初始化", 5),
            ("用户认证模块", 8),
            ("商品管理模块", 8),
            ("订单管理模块", 8),
            ("购物车模块", 5),
            ("支付集成", 5),
            ("测试与修复", 5),
            ("部署配置", 6),
        ]
        
        turn_count = 1
        chapter_count = 1
        all_summaries = []
        
        total_start = time.time()
        
        for phase_name, phase_turns in phases:
            phase_start = time.time()
            phase_summaries = []
            
            for phase_step in range(1, phase_turns + 1):
                user_intent = self._generate_user_intent(phase_name, phase_step, phase_turns)
                assistant_action = self._generate_assistant_action(phase_name, phase_step)
                tool_calls = self._generate_tool_calls(phase_name, phase_step, turn_count)
                
                summary = summarize_turn(
                    user_message=user_intent,
                    assistant_response="我来帮你完成这个任务。",
                    tool_calls_detail=tool_calls,
                )
                
                state.add_turn_summary(
                    turn_number=turn_count,
                    user_intent=summary["user_intent"],
                    assistant_action=summary["assistant_action"],
                    result_summary=summary["result_summary"],
                    files_touched=[tc["args"].get("file_path", tc["args"].get("path", "")) for tc in tool_calls if tc.get("name") in ["write_file", "patch", "read_file"]],
                )
                
                phase_summaries.append({
                    "turn_number": turn_count,
                    "user_intent": summary["user_intent"],
                    "assistant_action": summary["assistant_action"],
                    "result_summary": summary["result_summary"],
                    "files_touched": [tc["args"].get("file_path", tc["args"].get("path", "")) for tc in tool_calls if tc.get("name") in ["write_file", "patch", "read_file"]],
                })
                
                all_summaries.append(summary)
                turn_count += 1
                
                if turn_count % 10 == 0:
                    chapter_summary = summarize_chapter(phase_summaries[-10:])
                    state.add_chapter_summary(
                        chapter_number=chapter_count,
                        start_turn=turn_count - 9,
                        end_turn=turn_count,
                        summary=chapter_summary["summary"],
                        key_decisions=chapter_summary.get("key_decisions", []),
                        key_files=chapter_summary.get("key_files", []),
                        key_technologies=chapter_summary.get("key_technologies", []),
                    )
                    chapter_count += 1
            
            phase_time = time.time() - phase_start
            print(f"  Phase '{phase_name}' completed in {phase_time:.1f}s ({phase_turns} turns)")
        
        total_time = time.time() - total_start
        
        assert turn_count - 1 == 50, f"Expected 50 turns, got {turn_count - 1}"
        assert len(state.turn_summaries) == min(50, state._max_turn_summaries)
        assert len(state.chapter_summaries) >= 4
        
        system_reminder = state.to_system_reminder()
        assert "电商" in system_reminder or "API" in system_reminder
        assert len(system_reminder) > 50
        
        print(f"\n=== 50轮对话测试完成 ===")
        print(f"总耗时: {total_time:.1f}秒")
        print(f"平均每轮: {total_time / 50:.2f}秒")
        print(f"系统提醒长度: {len(system_reminder)}字符")
        print(f"章节摘要数量: {len(state.chapter_summaries)}")
        print(f"决策记录数量: {len(state.decisions_made)}")
        print(f"文件变更记录数量: {len(state.file_change_log)}")
        
        return state
    
    def _generate_user_intent(self, phase_name: str, step: int, total_steps: int) -> str:
        intents = {
            "项目初始化": [
                "创建项目结构和基础配置",
                "设置FastAPI框架和依赖",
                "配置数据库连接",
                "创建基础目录结构",
                "配置日志和异常处理",
            ],
            "用户认证模块": [
                "创建用户模型和数据库表",
                "实现用户注册接口",
                "实现用户登录接口",
                "集成JWT token生成",
                "实现密码加密和验证",
                "添加认证中间件",
                "实现用户信息查询接口",
                "实现密码重置功能",
            ],
            "商品管理模块": [
                "创建商品分类模型",
                "创建商品模型",
                "实现商品列表接口",
                "实现商品详情接口",
                "实现商品创建接口",
                "实现商品更新接口",
                "实现商品搜索功能",
                "实现库存管理",
            ],
            "订单管理模块": [
                "创建订单模型",
                "创建订单项模型",
                "实现创建订单接口",
                "实现订单列表接口",
                "实现订单详情接口",
                "实现订单状态更新",
                "实现订单取消功能",
                "实现订单统计接口",
            ],
            "购物车模块": [
                "创建购物车模型",
                "实现添加商品到购物车",
                "实现购物车列表接口",
                "实现更新购物车数量",
                "实现清空购物车",
            ],
            "支付集成": [
                "配置支付网关",
                "实现支付接口",
                "实现支付回调处理",
                "实现退款功能",
                "添加支付状态查询",
            ],
            "测试与修复": [
                "运行单元测试",
                "修复认证模块bug",
                "修复订单模块bug",
                "优化API响应时间",
                "添加错误处理",
            ],
            "部署配置": [
                "创建Dockerfile",
                "创建docker-compose.yml",
                "配置Nginx反向代理",
                "配置环境变量",
                "创建启动脚本",
                "配置CI/CD流程",
            ],
        }
        return intents[phase_name][step - 1]
    
    def _generate_assistant_action(self, phase_name: str, step: int) -> str:
        actions = {
            "项目初始化": ["创建main.py", "配置requirements.txt", "配置数据库", "创建目录", "配置logging"],
            "用户认证模块": ["创建User模型", "实现注册", "实现登录", "集成JWT", "密码加密", "中间件", "用户查询", "密码重置"],
            "商品管理模块": ["分类模型", "商品模型", "列表接口", "详情接口", "创建接口", "更新接口", "搜索", "库存"],
            "订单管理模块": ["订单模型", "订单项模型", "创建订单", "订单列表", "订单详情", "状态更新", "取消订单", "统计"],
            "购物车模块": ["购物车模型", "添加商品", "购物车列表", "更新数量", "清空"],
            "支付集成": ["配置支付", "支付接口", "回调处理", "退款", "状态查询"],
            "测试与修复": ["运行测试", "修复认证bug", "修复订单bug", "优化性能", "错误处理"],
            "部署配置": ["Dockerfile", "docker-compose", "Nginx", "环境变量", "启动脚本", "CI/CD"],
        }
        return f"实现{actions[phase_name][step - 1]}"
    
    def _generate_tool_calls(self, phase_name: str, step: int, turn: int) -> list[dict]:
        tool_map = {
            "项目初始化": [
                [{"name": "write_file", "args": {"file_path": "main.py"}}],
                [{"name": "write_file", "args": {"file_path": "requirements.txt"}}],
                [{"name": "write_file", "args": {"file_path": "database.py"}}],
                [{"name": "terminal", "args": {"command": "mkdir -p models routes utils tests"}}],
                [{"name": "write_file", "args": {"file_path": "logging.py"}}],
            ],
            "用户认证模块": [
                [{"name": "write_file", "args": {"file_path": "models/user.py"}}],
                [{"name": "write_file", "args": {"file_path": "routes/auth.py"}}],
                [{"name": "patch", "args": {"path": "routes/auth.py", "content": "add login endpoint"}}],
                [{"name": "write_file", "args": {"file_path": "utils/jwt.py"}}],
                [{"name": "write_file", "args": {"file_path": "utils/password.py"}}],
                [{"name": "write_file", "args": {"file_path": "middleware/auth.py"}}],
                [{"name": "patch", "args": {"path": "routes/auth.py", "content": "add user info endpoint"}}],
                [{"name": "patch", "args": {"path": "routes/auth.py", "content": "add password reset"}}],
            ],
            "商品管理模块": [
                [{"name": "write_file", "args": {"file_path": "models/category.py"}}],
                [{"name": "write_file", "args": {"file_path": "models/product.py"}}],
                [{"name": "write_file", "args": {"file_path": "routes/products.py"}}],
                [{"name": "patch", "args": {"path": "routes/products.py", "content": "add detail endpoint"}}],
                [{"name": "patch", "args": {"path": "routes/products.py", "content": "add create endpoint"}}],
                [{"name": "patch", "args": {"path": "routes/products.py", "content": "add update endpoint"}}],
                [{"name": "write_file", "args": {"file_path": "services/search.py"}}],
                [{"name": "write_file", "args": {"file_path": "services/inventory.py"}}],
            ],
            "订单管理模块": [
                [{"name": "write_file", "args": {"file_path": "models/order.py"}}],
                [{"name": "write_file", "args": {"file_path": "models/order_item.py"}}],
                [{"name": "write_file", "args": {"file_path": "routes/orders.py"}}],
                [{"name": "patch", "args": {"path": "routes/orders.py", "content": "add list endpoint"}}],
                [{"name": "patch", "args": {"path": "routes/orders.py", "content": "add detail endpoint"}}],
                [{"name": "patch", "args": {"path": "routes/orders.py", "content": "add status update"}}],
                [{"name": "patch", "args": {"path": "routes/orders.py", "content": "add cancel endpoint"}}],
                [{"name": "write_file", "args": {"file_path": "services/order_stats.py"}}],
            ],
            "购物车模块": [
                [{"name": "write_file", "args": {"file_path": "models/cart.py"}}],
                [{"name": "write_file", "args": {"file_path": "routes/cart.py"}}],
                [{"name": "patch", "args": {"path": "routes/cart.py", "content": "add list endpoint"}}],
                [{"name": "patch", "args": {"path": "routes/cart.py", "content": "add update endpoint"}}],
                [{"name": "patch", "args": {"path": "routes/cart.py", "content": "add clear endpoint"}}],
            ],
            "支付集成": [
                [{"name": "write_file", "args": {"file_path": "services/payment.py"}}],
                [{"name": "write_file", "args": {"file_path": "routes/payment.py"}}],
                [{"name": "patch", "args": {"path": "routes/payment.py", "content": "add webhook"}}],
                [{"name": "patch", "args": {"path": "routes/payment.py", "content": "add refund"}}],
                [{"name": "patch", "args": {"path": "routes/payment.py", "content": "add status query"}}],
            ],
            "测试与修复": [
                [{"name": "terminal", "args": {"command": "pytest -v"}}],
                [{"name": "read_file", "args": {"file_path": "routes/auth.py"}}],
                [{"name": "patch", "args": {"path": "routes/auth.py", "content": "fix auth bug"}}],
                [{"name": "read_file", "args": {"file_path": "routes/orders.py"}}],
                [{"name": "patch", "args": {"path": "routes/orders.py", "content": "fix order bug"}}],
            ],
            "部署配置": [
                [{"name": "write_file", "args": {"file_path": "Dockerfile"}}],
                [{"name": "write_file", "args": {"file_path": "docker-compose.yml"}}],
                [{"name": "write_file", "args": {"file_path": "nginx.conf"}}],
                [{"name": "write_file", "args": {"file_path": ".env.production"}}],
                [{"name": "write_file", "args": {"file_path": "start.sh"}}],
                [{"name": "write_file", "args": {"file_path": ".github/workflows/deploy.yml"}}],
            ],
        }
        return tool_map[phase_name][step - 1]


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class TestLongConversationMemoryMetrics:
    def test_memory_recall_accuracy(self):
        state = ConversationState()
        state.update_conversation_goal("开发任务管理系统")
        
        key_points = []
        summaries_for_chapters = []
        
        for i in range(1, 31):
            if i == 1:
                user_msg = "创建项目，使用FastAPI和SQLAlchemy"
                key_points.append("FastAPI")
            elif i == 5:
                user_msg = "使用PostgreSQL作为数据库"
                key_points.append("PostgreSQL")
            elif i == 10:
                user_msg = "集成Redis缓存"
                key_points.append("Redis")
            elif i == 15:
                user_msg = "添加JWT认证"
                key_points.append("JWT")
            elif i == 20:
                user_msg = "实现WebSocket实时通知"
                key_points.append("WebSocket")
            elif i == 25:
                user_msg = "添加Celery异步任务"
                key_points.append("Celery")
            else:
                user_msg = f"第{i}轮：继续开发"
            
            summary = summarize_turn(user_msg, "执行开发操作", [])
            state.add_turn_summary(i, summary["user_intent"], summary["assistant_action"], summary["result_summary"])
            
            summaries_for_chapters.append({
                "turn_number": i,
                "user_intent": summary["user_intent"],
                "assistant_action": summary["assistant_action"],
                "result_summary": summary["result_summary"],
                "files_touched": [],
            })
            
            if i % 10 == 0:
                chapter_summary = summarize_chapter(summaries_for_chapters[-10:])
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
        
        print(f"\n=== 记忆召回测试 ===")
        print(f"关键要点: {key_points}")
        print(f"召回要点: {matched_points}")
        print(f"召回率: {recall_rate:.1%}")
        print(f"系统提醒: {reminder[:500]}...")
        print(f"章节摘要数量: {len(state.chapter_summaries)}")
        
        assert recall_rate >= 0.6, f"记忆召回率不足: {recall_rate:.1%}"
    
    def test_chapter_summary_coherence(self):
        summaries = []
        for i in range(1, 21):
            summaries.append({
                "turn_number": i,
                "user_intent": f"第{i}轮用户意图",
                "assistant_action": f"第{i}轮助手操作",
                "result_summary": "完成",
                "files_touched": [f"file{i}.py"],
            })
        
        chapter1 = summarize_chapter(summaries[:10])
        chapter2 = summarize_chapter(summaries[10:])
        
        combined_summary = chapter1["summary"] + " " + chapter2["summary"]
        
        print(f"\n=== 章节摘要连贯性测试 ===")
        print(f"章节1摘要长度: {len(chapter1['summary'])}")
        print(f"章节2摘要长度: {len(chapter2['summary'])}")
        print(f"章节1关键文件: {chapter1.get('key_files', [])}")
        print(f"章节2关键文件: {chapter2.get('key_files', [])}")
        
        assert len(chapter1["summary"]) > 20
        assert len(chapter2["summary"]) > 20
        assert len(chapter1.get("key_files", [])) > 0 or len(chapter1.get("key_decisions", [])) > 0
