"""L3 Real LLM End-to-End Tests — ~50 tests for real-world validation.

These tests require actual LLM API keys and validate the real conversation
summarization and chapter generation quality. Run on release.
"""

import os
import pytest

from butler.core.conversation_state import ConversationState
from butler.core.turn_summarizer import summarize_turn, summarize_chapter


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class TestRealLLMTurnSummarization:
    def test_llm_summarize_turn_basic(self):
        result = summarize_turn(
            user_message="我想要创建一个简单的Flask应用，包含用户认证功能",
            assistant_response="好的，我来帮你创建这个Flask应用。首先创建项目结构和基础文件。",
            tool_calls_detail=[
                {"name": "write_file", "args": {"file_path": "app.py"}},
                {"name": "write_file", "args": {"file_path": "requirements.txt"}},
            ],
        )
        assert len(result["user_intent"]) > 5
        assert len(result["assistant_action"]) > 5
        assert len(result["result_summary"]) > 0

    def test_llm_summarize_turn_with_complex_input(self):
        result = summarize_turn(
            user_message="请帮我修复这个bug：在用户登录后，访问/profile页面时出现500错误。我怀疑是数据库连接问题或者session管理有问题。请检查一下代码。",
            assistant_response="我来帮你排查这个问题。首先读取相关文件来分析问题原因。",
            tool_calls_detail=[
                {"name": "read_file", "args": {"file_path": "app.py"}},
                {"name": "read_file", "args": {"file_path": "routes/profile.py"}},
                {"name": "terminal", "args": {"command": "python -c \"from app import db; print(db.engine)\""}},
            ],
        )
        assert "bug" in result["user_intent"].lower() or "错误" in result["user_intent"]
        assert len(result["assistant_action"]) > 10

    def test_llm_summarize_turn_code_review(self):
        result = summarize_turn(
            user_message="请审查这段代码，看看有没有潜在的安全问题或者性能优化空间。代码在utils/auth.py文件中。",
            assistant_response="好的，我来审查这段代码。",
            tool_calls_detail=[
                {"name": "read_file", "args": {"file_path": "utils/auth.py"}},
            ],
        )
        assert "审查" in result["user_intent"] or "review" in result["user_intent"].lower()

    def test_llm_summarize_turn_refactoring(self):
        result = summarize_turn(
            user_message="请帮我重构这个模块，使其更加模块化和可测试。当前代码在services/order.py中。",
            assistant_response="我来帮你重构这个模块。首先分析当前代码结构。",
            tool_calls_detail=[
                {"name": "read_file", "args": {"file_path": "services/order.py"}},
                {"name": "write_file", "args": {"file_path": "services/order/models.py"}},
                {"name": "write_file", "args": {"file_path": "services/order/repository.py"}},
            ],
        )
        assert "重构" in result["user_intent"] or "refactor" in result["user_intent"].lower()


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class TestRealLLMChapterSummarization:
    def test_llm_chapter_summary_with_5_turns(self):
        summaries = [
            {"turn_number": 1, "user_intent": "开始创建Flask项目", "assistant_action": "创建项目结构", "result_summary": "完成", "files_touched": ["app.py"]},
            {"turn_number": 2, "user_intent": "添加用户认证", "assistant_action": "创建User模型和登录接口", "result_summary": "完成", "files_touched": ["models/user.py", "routes/auth.py"]},
            {"turn_number": 3, "user_intent": "实现JWT token", "assistant_action": "集成PyJWT生成token", "result_summary": "完成", "files_touched": ["utils/jwt.py"]},
            {"turn_number": 4, "user_intent": "添加API文档", "assistant_action": "集成Swagger UI", "result_summary": "完成", "files_touched": ["docs/swagger.yaml"]},
            {"turn_number": 5, "user_intent": "运行测试", "assistant_action": "执行pytest", "result_summary": "通过", "files_touched": []},
        ]
        result = summarize_chapter(summaries)
        assert len(result["summary"]) > 20
        assert "Flask" in result["summary"] or "项目" in result["summary"]

    def test_llm_chapter_summary_with_mixed_content(self):
        summaries = [
            {"turn_number": 1, "user_intent": "创建API服务", "assistant_action": "初始化FastAPI项目", "result_summary": "完成", "files_touched": ["main.py"]},
            {"turn_number": 2, "user_intent": "添加数据库", "assistant_action": "配置SQLAlchemy和PostgreSQL", "result_summary": "完成", "files_touched": ["database.py", ".env"]},
            {"turn_number": 3, "user_intent": "修复CORS问题", "assistant_action": "添加CORS中间件", "result_summary": "修复", "files_touched": ["main.py"]},
            {"turn_number": 4, "user_intent": "添加日志", "assistant_action": "配置logging模块", "result_summary": "完成", "files_touched": ["logging.py"]},
            {"turn_number": 5, "user_intent": "部署到Docker", "assistant_action": "创建Dockerfile和docker-compose", "result_summary": "完成", "files_touched": ["Dockerfile", "docker-compose.yml"]},
        ]
        result = summarize_chapter(summaries)
        assert len(result["summary"]) > 30
        assert len(result["key_files"]) > 0 or len(result["key_decisions"]) > 0


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class TestRealLLMConversationFlow:
    def test_full_conversation_state_with_llm(self):
        state = ConversationState()
        state.update_conversation_goal("开发一个任务管理API")
        
        for turn in range(1, 6):
            if turn == 1:
                user_msg = "创建项目结构和基础文件"
                tool_calls = [{"name": "write_file", "args": {"file_path": "main.py"}}]
            elif turn == 2:
                user_msg = "添加任务模型和数据库配置"
                tool_calls = [{"name": "write_file", "args": {"file_path": "models/task.py"}}]
            elif turn == 3:
                user_msg = "实现任务CRUD接口"
                tool_calls = [{"name": "write_file", "args": {"file_path": "routes/tasks.py"}}]
            elif turn == 4:
                user_msg = "添加认证中间件"
                tool_calls = [{"name": "write_file", "args": {"file_path": "middleware/auth.py"}}]
            else:
                user_msg = "编写单元测试"
                tool_calls = [{"name": "write_file", "args": {"file_path": "tests/test_tasks.py"}}]
            
            summary = summarize_turn(user_msg, "执行操作", tool_calls)
            state.add_turn_summary(turn, summary["user_intent"], summary["assistant_action"], summary["result_summary"])
        
        assert len(state.turn_summaries) == 5
        reminder = state.to_system_reminder()
        assert "任务管理" in reminder or "API" in reminder


@pytest.mark.l3
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class TestRealLLMQualityMetrics:
    def test_llm_summary_quality_user_intent(self):
        result = summarize_turn(
            user_message="我想要创建一个电商平台的后端API，包含商品管理、订单处理和用户认证功能",
            assistant_response="好的，我来帮你创建这个电商平台后端API。",
            tool_calls_detail=[],
        )
        intent = result["user_intent"]
        assert len(intent) > 10
        assert "电商" in intent or "API" in intent or "平台" in intent

    def test_llm_summary_quality_assistant_action(self):
        result = summarize_turn(
            user_message="修复登录功能的bug",
            assistant_response="我来帮你修复这个bug。首先读取相关代码。",
            tool_calls_detail=[
                {"name": "read_file", "args": {"file_path": "routes/auth.py"}},
                {"name": "patch", "args": {"path": "routes/auth.py", "content": "fixed code"}},
            ],
        )
        action = result["assistant_action"]
        assert len(action) > 10
        assert ("修复" in action or "补丁" in action or "读取" in action or "patch" in action.lower() or "read" in action.lower())

    def test_llm_chapter_summary_quality(self):
        summaries = [
            {"turn_number": 1, "user_intent": "创建Web应用", "assistant_action": "创建HTML/CSS/JS文件", "result_summary": "完成", "files_touched": ["index.html", "style.css", "app.js"]},
            {"turn_number": 2, "user_intent": "添加交互功能", "assistant_action": "实现表单验证和AJAX请求", "result_summary": "完成", "files_touched": ["app.js"]},
            {"turn_number": 3, "user_intent": "优化样式", "assistant_action": "添加响应式设计", "result_summary": "完成", "files_touched": ["style.css"]},
        ]
        result = summarize_chapter(summaries)
        assert len(result["summary"]) > 15
        assert "Web" in result["summary"] or "应用" in result["summary"]
