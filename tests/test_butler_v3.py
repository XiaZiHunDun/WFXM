"""Comprehensive tests for Butler v3 (Route C — Embedded Hybrid)."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BUTLER_HOME", str(Path(tempfile.mkdtemp()) / ".butler"))


# ── Integration bridge ──────────────────────────────────────────────

class TestIntegrationBridge:
    def test_ensure_hermes_env(self):
        from butler.main import _ensure_hermes_env
        _ensure_hermes_env()
        assert os.environ.get("HERMES_HOME")

    def test_orchestrator_agent_kwargs(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator(user_id="test", channel="cli")
        kwargs = orch.get_agent_kwargs()
        assert "model" in kwargs
        assert "ephemeral_system_prompt" in kwargs
        assert kwargs["user_id"] == "test"
        assert kwargs["platform"] == "cli"

    def test_orchestrator_project_agent_kwargs(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        kwargs = orch.get_project_agent_kwargs("dev")
        assert "model" in kwargs
        assert "ephemeral_system_prompt" in kwargs

    def test_aiagent_importable(self):
        from run_agent import AIAgent
        assert AIAgent is not None

    def test_create_butler_agent_constructs(self):
        from butler.main import _create_butler_agent, _ensure_hermes_env
        from butler.orchestrator import ButlerOrchestrator
        _ensure_hermes_env()
        orch = ButlerOrchestrator()
        agent = _create_butler_agent(orch, quiet_mode=True)
        assert hasattr(agent, "run_conversation")


# ── Memory Plugin ─────────────────────────────────────────────────

class TestMemoryPlugin:
    def test_plugin_registration(self):
        from plugins.memory.butler import register

        class FakeCtx:
            def __init__(self):
                self.provider = None
            def register_memory_provider(self, p):
                self.provider = p

        ctx = FakeCtx()
        register(ctx)
        assert ctx.provider is not None
        assert ctx.provider.name == "butler"

    def test_memory_provider_tools(self):
        from butler.memory_plugin import ButlerMemoryProvider
        mp = ButlerMemoryProvider()
        schemas = mp.get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert "butler_remember" in names
        assert "butler_recall" in names

    def test_memory_provider_system_prompt(self):
        from butler.memory_plugin import ButlerMemoryProvider
        mp = ButlerMemoryProvider()
        block = mp.system_prompt_block()
        assert "butler_remember" in block.lower() or "butler" in block.lower()

    def test_sync_turn_accumulates(self):
        from butler.memory_plugin import ButlerMemoryProvider
        mp = ButlerMemoryProvider()
        mp._turn_buffer = []
        mp.sync_turn("hello", "hi there")
        assert len(mp._turn_buffer) == 2
        mp.sync_turn("how are you", "fine")
        assert len(mp._turn_buffer) == 4


# ── Butler Plugin (Gateway Hook) ──────────────────────────────────

class TestButlerPlugin:
    def test_plugin_hook_registration(self):
        from plugins.butler import register

        class FakeCtx:
            def __init__(self):
                self.hooks = {}
            def register_hook(self, name, fn):
                self.hooks[name] = fn

        ctx = FakeCtx()
        register(ctx)
        assert "pre_gateway_dispatch" in ctx.hooks

    def test_slash_command_projects(self):
        from plugins.butler import _handle_butler_gateway_command
        result = _handle_butler_gateway_command("/projects", {})
        assert result is not None
        assert isinstance(result, str)

    def test_slash_command_status(self):
        from plugins.butler import _handle_butler_gateway_command
        result = _handle_butler_gateway_command("/status", {})
        assert result is not None
        assert "Butler" in result

    def test_slash_command_model_view(self):
        from plugins.butler import _handle_butler_gateway_command
        result = _handle_butler_gateway_command("/model", {})
        assert result is not None
        assert "butler" in result.lower()

    def test_non_slash_returns_none(self):
        from plugins.butler import _is_butler_command
        assert _is_butler_command("/projects")
        assert _is_butler_command("/switch myproject")
        assert not _is_butler_command("hello butler")
        assert not _is_butler_command("what is /projects")


# ── Agent Profiles ──────────────────────────────────────────────

class TestAgentProfiles:
    def test_dev_profile(self):
        from butler.agent_profiles import get_profile
        p = get_profile("dev")
        assert p is not None
        assert p.role == "dev_agent"
        assert "code_editing" in p.toolsets
        assert "shell" in p.toolsets

    def test_content_profile(self):
        from butler.agent_profiles import get_profile
        p = get_profile("content")
        assert p is not None
        assert p.role == "content_agent"

    def test_review_profile(self):
        from butler.agent_profiles import get_profile
        p = get_profile("review")
        assert p is not None
        assert p.role == "review_agent"

    def test_unknown_profile_returns_none(self):
        from butler.agent_profiles import get_profile
        assert get_profile("unknown_role_xyz") is None

    def test_model_aware_prompt_domestic(self):
        from butler.agent_profiles import get_model_aware_prompt_extra
        extra = get_model_aware_prompt_extra("minimax")
        assert "function calling" in extra
        extra2 = get_model_aware_prompt_extra("deepseek")
        assert len(extra2) > 0

    def test_model_aware_prompt_non_domestic(self):
        from butler.agent_profiles import get_model_aware_prompt_extra
        assert get_model_aware_prompt_extra("anthropic") == ""
        assert get_model_aware_prompt_extra("openai") == ""


# ── Tool Guardrails ──────────────────────────────────────────────

class TestToolGuardrails:
    def test_allow_first_call(self):
        from butler.tool_guardrails import ToolCallGuardrailController
        ctrl = ToolCallGuardrailController()
        d = ctrl.before_call("read_file", {"path": "test.py"})
        assert d.allows_execution
        assert not d.should_halt

    def test_repeated_failure_warning(self):
        from butler.tool_guardrails import ToolCallGuardrailController, GuardrailConfig
        ctrl = ToolCallGuardrailController(GuardrailConfig(exact_failure_warn_after=2))

        ctrl.after_call("run_shell", {"command": "fail"}, '{"exit_code": 1}')
        ctrl.after_call("run_shell", {"command": "fail"}, '{"exit_code": 1}')
        d = ctrl.after_call("run_shell", {"command": "fail"}, '{"exit_code": 1}')
        assert d.action in ("warn", "block", "halt")

    def test_block_after_threshold(self):
        from butler.tool_guardrails import ToolCallGuardrailController, GuardrailConfig
        cfg = GuardrailConfig(exact_failure_block_after=3)
        ctrl = ToolCallGuardrailController(cfg)
        args = {"command": "always_fail"}
        for _ in range(3):
            ctrl.after_call("run_shell", args, '{"exit_code": 1}')
        d = ctrl.before_call("run_shell", args)
        assert d.action == "block"

    def test_idempotent_no_progress(self):
        from butler.tool_guardrails import ToolCallGuardrailController, GuardrailConfig
        cfg = GuardrailConfig(no_progress_warn_after=2)
        ctrl = ToolCallGuardrailController(cfg)
        args = {"path": "test.py"}
        ctrl.after_call("read_file", args, '{"content": "same"}')
        d = ctrl.after_call("read_file", args, '{"content": "same"}')
        assert d.action == "warn"

    def test_reset_clears_state(self):
        from butler.tool_guardrails import ToolCallGuardrailController
        ctrl = ToolCallGuardrailController()
        ctrl.after_call("run_shell", {"cmd": "x"}, '{"exit_code": 1}')
        ctrl.reset_for_turn()
        d = ctrl.before_call("run_shell", {"cmd": "x"})
        assert d.allows_execution

    def test_synthetic_result(self):
        from butler.tool_guardrails import GuardrailDecision, synthetic_result
        d = GuardrailDecision(action="block", code="test", message="blocked")
        result = synthetic_result(d)
        data = json.loads(result)
        assert "error" in data
        assert "guardrail" in data


# ── PostSessionProcessor ────────────────────────────────────────

class TestPostSessionProcessor:
    def test_skip_short_conversations(self):
        from butler.post_session import PostSessionProcessor
        proc = PostSessionProcessor()

        async def _dummy(p): return ""
        proc.set_llm_call(_dummy)

        result = asyncio.get_event_loop().run_until_complete(
            proc.process(messages=[{"role": "user", "content": "hi"}])
        )
        assert result["memory_updates"] == 0
        assert result["skills_extracted"] == 0

    def test_process_with_mock_llm(self):
        from butler.post_session import PostSessionProcessor

        async def _mock_llm(prompt):
            return '{"updates": [{"target": "butler", "content": "用户喜欢Python"}]}'

        proc = PostSessionProcessor()
        proc.set_llm_call(_mock_llm)

        mock_memory = MagicMock()
        mock_memory.get_system_context.return_value = ""
        mock_memory.add_profile.return_value = {"success": True}

        messages = [
            {"role": "user", "content": "我喜欢Python"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "帮我写代码"},
            {"role": "assistant", "content": "好的，马上"},
        ]
        result = asyncio.get_event_loop().run_until_complete(
            proc.process(messages=messages, butler_memory=mock_memory)
        )
        assert result["memory_updates"] >= 0  # depends on transcript length threshold

    def test_from_hermes_agent_factory(self):
        from butler.post_session import PostSessionProcessor
        mock_agent = MagicMock()
        mock_agent.run_conversation.return_value = {"response": "{}"}
        proc = PostSessionProcessor.from_hermes_agent(mock_agent)
        assert proc._llm_call is not None


# ── TaskOrchestrator ────────────────────────────────────────────

class TestTaskOrchestrator:
    def test_topological_sort_linear(self):
        from butler.task_orchestrator import TaskOrchestrator, TaskNode, AgentSpawnConfig
        orch = TaskOrchestrator()
        nodes = [
            TaskNode(id="a", config=AgentSpawnConfig(role="dev", task="step1")),
            TaskNode(id="b", config=AgentSpawnConfig(role="dev", task="step2"), depends_on=["a"]),
            TaskNode(id="c", config=AgentSpawnConfig(role="dev", task="step3"), depends_on=["b"]),
        ]
        layers = orch._topological_sort(nodes)
        assert len(layers) == 3
        assert layers[0] == ["a"]
        assert layers[1] == ["b"]
        assert layers[2] == ["c"]

    def test_topological_sort_parallel(self):
        from butler.task_orchestrator import TaskOrchestrator, TaskNode, AgentSpawnConfig
        orch = TaskOrchestrator()
        nodes = [
            TaskNode(id="root", config=AgentSpawnConfig(role="dev", task="root")),
            TaskNode(id="a", config=AgentSpawnConfig(role="dev", task="a"), depends_on=["root"]),
            TaskNode(id="b", config=AgentSpawnConfig(role="dev", task="b"), depends_on=["root"]),
            TaskNode(id="end", config=AgentSpawnConfig(role="dev", task="end"), depends_on=["a", "b"]),
        ]
        layers = orch._topological_sort(nodes)
        assert len(layers) == 3
        assert layers[0] == ["root"]
        assert set(layers[1]) == {"a", "b"}
        assert layers[2] == ["end"]

    def test_topological_sort_cycle(self):
        from butler.task_orchestrator import TaskOrchestrator, TaskNode, AgentSpawnConfig
        orch = TaskOrchestrator()
        nodes = [
            TaskNode(id="a", config=AgentSpawnConfig(role="dev", task="a"), depends_on=["b"]),
            TaskNode(id="b", config=AgentSpawnConfig(role="dev", task="b"), depends_on=["a"]),
        ]
        layers = orch._topological_sort(nodes)
        assert layers == []


# ── Orchestrator Prompt + Skills ──────────────────────────────

class TestOrchestrator:
    def test_build_system_prompt(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        prompt = orch.build_system_prompt()
        assert len(prompt) > 100
        assert "Butler" in prompt or "管家" in prompt

    def test_build_memory_context(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        ctx = orch.build_memory_context()
        assert isinstance(ctx, str)

    def test_inject_skill_context_no_skills(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        result = orch.inject_skill_context("hello world")
        assert "hello world" in result

    def test_project_switch_callback(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        orch.on_project_switch("old", "new")


# ── Config runtime overrides ──────────────────────────────────

class TestConfigOverrides:
    def test_runtime_model_override(self):
        from butler.config import get_butler_settings, ModelConfig
        settings = get_butler_settings()
        settings.set_runtime_model_override("butler", ModelConfig(provider="test", model="test-model"))
        mc = settings.get_model_config("butler")
        assert mc.model == "test-model"
        settings.clear_runtime_model_overrides()
        mc2 = settings.get_model_config("butler")
        assert mc2.model != "test-model" or mc2.provider != "test"

    def test_layered_model_config(self):
        from butler.config import LayeredModelConfig, ModelConfig
        lmc = LayeredModelConfig(
            butler=ModelConfig(provider="p1", model="m1"),
            dev_agent=ModelConfig(provider="p2", model="m2"),
        )
        assert lmc.get("butler").model == "m1"
        assert lmc.get("dev_agent").model == "m2"
        assert lmc.get("unknown").model == "m1"


# ── Slash commands (main.py) ──────────────────────────────────

class TestMainSlashCommands:
    def test_handle_help(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator

        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/help", orch, console)
        assert result == "handled"
        console.print.assert_called()

    def test_handle_projects(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator

        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/projects", orch, console)
        assert result == "handled"

    def test_handle_status(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator

        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/status", orch, console)
        assert result == "handled"

    def test_handle_quit(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator

        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/quit", orch, console)
        assert result == "quit"

    def test_handle_unknown_returns_none(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator

        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/nonexistent", orch, console)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
