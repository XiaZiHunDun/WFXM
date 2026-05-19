"""Session lifecycle memory coordination tests."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.session_lifecycle import (
    attach_turn_memory_prefetch,
    build_memory_pre_llm_transform,
    inject_turn_memory,
    sync_turn_memory,
    trigger_session_end,
)


def _orch() -> MagicMock:
    orch = MagicMock()
    orch.project_manager.current_project = "proj"
    orch.butler_memory.get_system_context.return_value = "global memory"
    orch.butler_memory.experience.search.return_value = [
        {"project": "proj", "content": "use pytest -q"}
    ]
    orch._project_memory.get_context_for_agent.return_value = "project memory"
    return orch


def test_inject_turn_memory_adds_relevant_context():
    orch = _orch()

    out = inject_turn_memory(orch, "run tests", role="dev")

    assert "## 相关记忆（Butler）" in out
    assert "global memory" in out
    assert "project memory" in out
    assert "use pytest -q" in out
    assert out.endswith("run tests")


def test_memory_pre_llm_transform_does_not_mutate_history_messages():
    orch = _orch()
    original = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "run tests"},
    ]
    diagnostics: dict[str, object] = {}

    transform = build_memory_pre_llm_transform(orch, "run tests", role="dev", diagnostics=diagnostics)
    out = transform(original)

    assert out is not original
    assert out[-1]["content"].startswith("## 相关记忆（Butler）")
    assert original[-1]["content"] == "run tests"
    assert diagnostics["memory_context_injected"] is True
    assert diagnostics["memory_context_chars"] > 0


def test_attach_turn_memory_prefetch_composes_existing_transform():
    orch = _orch()
    loop = MagicMock()
    loop.callbacks.pre_llm_transform = lambda messages: messages + [{"role": "user", "content": "existing"}]

    attach_turn_memory_prefetch(loop, orch, "clean query", role="butler")
    out = loop.callbacks.pre_llm_transform([{"role": "user", "content": "clean query"}])

    assert out[-2]["content"].startswith("## 相关记忆（Butler）")
    assert out[-1]["content"] == "existing"


def test_attach_turn_memory_prefetch_replaces_previous_memory_transform():
    orch = _orch()
    loop = MagicMock()
    loop.callbacks.pre_llm_transform = None

    attach_turn_memory_prefetch(loop, orch, "first", role="butler")
    attach_turn_memory_prefetch(loop, orch, "second", role="butler")
    out = loop.callbacks.pre_llm_transform([{"role": "user", "content": "augmented"}])

    rendered = out[-1]["content"]
    assert rendered.count("## 相关记忆（Butler）") == 1
    search_queries = [call.args[0] for call in orch.butler_memory.experience.search.call_args_list]
    assert search_queries == ["second"]


def test_memory_transform_searches_with_clean_query_not_augmented_content():
    orch = _orch()
    transform = build_memory_pre_llm_transform(orch, "clean query", role="butler")

    transform([{"role": "user", "content": "## skill context\n\naugmented"}])

    orch.butler_memory.experience.search.assert_called_with(
        "clean query",
        project="proj",
        limit=5,
    )


def test_inject_turn_memory_returns_original_when_no_context():
    orch = _orch()
    orch.butler_memory.get_system_context.return_value = "(No Butler-level memory yet.)"
    orch.butler_memory.experience.search.return_value = []
    orch._project_memory.get_context_for_agent.return_value = "(No project memory yet.)"

    assert inject_turn_memory(orch, "hello") == "hello"


def test_sync_turn_memory_skips_interrupted_and_failed_status():
    orch = _orch()

    sync_turn_memory(orch, "q", "a", interrupted=True)
    sync_turn_memory(orch, "q", "a", status=LoopStatus.ERROR)

    orch.butler_memory.experience.add.assert_not_called()


def test_sync_turn_memory_records_success_and_provider():
    orch = _orch()
    provider = MagicMock()
    orch.memory_provider = provider

    result = sync_turn_memory(orch, "question", "answer", status=LoopStatus.COMPLETED)

    assert result["experience_updates"] == 1
    assert result["provider_synced"] is True
    orch.butler_memory.experience.add.assert_called_once()
    provider.sync_turn.assert_called_once_with("question", "answer", session_id="")


def test_sync_turn_memory_provider_failure_keeps_experience_success():
    orch = _orch()
    provider = MagicMock()
    provider.sync_turn.side_effect = RuntimeError("provider down")
    orch.memory_provider = provider

    result = sync_turn_memory(orch, "question", "answer", status=LoopStatus.COMPLETED)

    assert result["skipped"] is False
    assert result["experience_updates"] == 1
    assert result["provider_synced"] is False
    assert result["provider_error"] == "provider down"


def test_trigger_session_end_returns_skipped_for_short_history():
    orch = _orch()
    loop = SimpleNamespace(messages=[{"role": "user"}, {"role": "assistant"}])

    result = trigger_session_end(orch, loop)

    assert result["skipped"] is True
    assert result["reason"] == "short_history"


def test_trigger_session_end_returns_processor_result():
    orch = _orch()
    loop = SimpleNamespace(messages=[
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "2"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "4"},
    ])
    processor = MagicMock()
    processor.process = MagicMock(return_value={"memory_updates": 1, "skills_extracted": 0, "errors": []})

    with patch("butler.post_session.PostSessionProcessor", return_value=processor):
        with patch("asyncio.run", return_value={"memory_updates": 1, "skills_extracted": 0, "errors": []}):
            result = trigger_session_end(orch, loop)

    assert result["memory_updates"] == 1
    processor.set_llm_call.assert_called_once()
