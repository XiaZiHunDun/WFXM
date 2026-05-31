"""Session lifecycle memory coordination tests."""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.session.lifecycle import (
    attach_turn_memory_prefetch,
    build_memory_pre_llm_transform,
    clear_session_boundary_memory,
    format_session_end_summary,
    inject_turn_memory,
    session_experience_tag,
    sync_turn_memory,
    trigger_session_end,
)


def _orch() -> MagicMock:
    from butler.memory.prefetch_cache import clear_prefetch_cache

    clear_prefetch_cache()
    orch = MagicMock()
    orch.project_manager.current_project = "proj"
    orch.project_manager.resolve_active_project_name.return_value = "proj"
    orch.project_manager.get_current.return_value = None
    orch.butler_memory.get_system_context.return_value = "global memory"
    orch.butler_memory.semantic = None
    orch.butler_memory.experience.search.return_value = [
        {"project": "proj", "content": "use pytest -q"}
    ]
    orch._project_memory.get_context_for_agent.return_value = "project memory"
    return orch


def test_inject_turn_memory_adds_relevant_context():
    orch = _orch()

    out = inject_turn_memory(orch, "run tests", role="dev")

    assert "<memory-context>" in out
    assert "global memory" in out
    assert "project memory" in out
    assert "use pytest -q" in out
    assert out.endswith("run tests")


def test_prefetch_skips_conversation_experience():
    orch = _orch()
    orch.butler_memory.experience.search.return_value = [
        {"project": "proj", "category": "conversation", "content": "Q: 秘密词XYZ → A: 好的"},
        {"project": "proj", "category": "experience", "content": "use pytest -q"},
    ]

    out = inject_turn_memory(orch, "我们刚才聊过什么？")

    assert "秘密词XYZ" not in out
    assert "use pytest -q" in out


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
    assert "<memory-context>" in out[-1]["content"]
    assert original[-1]["content"] == "run tests"
    assert diagnostics["memory_context_injected"] is True
    assert diagnostics["memory_context_chars"] > 0


def test_attach_turn_memory_prefetch_composes_existing_transform():
    orch = _orch()
    loop = MagicMock()
    loop.callbacks.pre_llm_transform = lambda messages: messages + [{"role": "user", "content": "existing"}]

    attach_turn_memory_prefetch(loop, orch, "clean query", role="butler")
    out = loop.callbacks.pre_llm_transform([{"role": "user", "content": "clean query"}])

    assert "<memory-context>" in out[-2]["content"]
    assert out[-1]["content"] == "existing"


def test_attach_turn_memory_prefetch_replaces_previous_memory_transform():
    orch = _orch()
    loop = MagicMock()
    loop.callbacks.pre_llm_transform = None

    attach_turn_memory_prefetch(loop, orch, "first", role="butler")
    attach_turn_memory_prefetch(loop, orch, "second", role="butler")
    out = loop.callbacks.pre_llm_transform([{"role": "user", "content": "augmented"}])

    rendered = out[-1]["content"]
    assert rendered.count("<memory-context>") == 1
    search_queries = [call.args[0] for call in orch.butler_memory.experience.search.call_args_list]
    assert search_queries == ["second"]


def test_memory_transform_searches_with_clean_query_not_augmented_content():
    from butler.memory.prefetch_cache import clear_prefetch_cache

    clear_prefetch_cache()
    orch = _orch()
    transform = build_memory_pre_llm_transform(orch, "clean query", role="butler")

    transform([{"role": "user", "content": "## skill context\n\naugmented"}])

    orch.butler_memory.experience.search.assert_called_with(
        "clean query",
        project="proj",
        limit=10,
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


def test_sync_turn_memory_skipped_when_conversation_sync_off(monkeypatch):
    monkeypatch.delenv("BUTLER_SYNC_CONVERSATION_MEMORY", raising=False)
    monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "0")
    orch = _orch()

    result = sync_turn_memory(orch, "question", "answer", status=LoopStatus.COMPLETED)

    assert result["skipped"] is True
    assert result["reason"] == "conversation_sync_off"
    orch.butler_memory.experience.add.assert_not_called()


def test_sync_turn_memory_records_on_explicit_remember(monkeypatch):
    monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "0")
    orch = _orch()

    result = sync_turn_memory(
        orch,
        "请记住：默认用灵文1号",
        "好的，已记住。",
        status=LoopStatus.COMPLETED,
        session_id="wechat:u1",
    )

    assert result["experience_updates"] == 1
    orch.butler_memory.experience.add.assert_called_once()


def test_sync_turn_memory_records_success_and_provider(monkeypatch):
    monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "1")
    orch = _orch()
    provider = MagicMock()
    orch.memory_provider = provider

    result = sync_turn_memory(
        orch,
        "question",
        "answer",
        status=LoopStatus.COMPLETED,
        session_id="wechat:u1",
    )

    assert result["experience_updates"] == 1
    assert result["provider_synced"] is True
    orch.butler_memory.experience.add.assert_called_once()
    add_kwargs = orch.butler_memory.experience.add.call_args.kwargs
    assert add_kwargs.get("tags") == session_experience_tag("wechat:u1")
    provider.sync_turn.assert_called_once_with("question", "answer", session_id="wechat:u1")


def test_sync_turn_memory_strips_private_tags_before_persist(monkeypatch):
    monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "1")
    orch = _orch()
    provider = MagicMock()
    orch.memory_provider = provider

    result = sync_turn_memory(
        orch,
        "公开问题 <private>secret-q</private>",
        "公开回答 <private>secret-a</private>",
        status=LoopStatus.COMPLETED,
        session_id="wechat:u1",
    )

    assert result["skipped"] is False
    add_kwargs = orch.butler_memory.experience.add.call_args.kwargs
    assert "secret-q" not in add_kwargs["content"]
    assert "secret-a" not in add_kwargs["content"]
    assert "公开问题" in add_kwargs["content"]
    assert "公开回答" in add_kwargs["content"]
    provider.sync_turn.assert_called_once_with("公开问题", "公开回答", session_id="wechat:u1")


def test_sync_turn_memory_skips_fully_private_turn(monkeypatch):
    monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "1")
    orch = _orch()
    provider = MagicMock()
    orch.memory_provider = provider

    result = sync_turn_memory(
        orch,
        "<private>secret-q</private>",
        "<private>secret-a</private>",
        status=LoopStatus.COMPLETED,
        session_id="wechat:u1",
    )

    assert result["skipped"] is True
    assert result["reason"] == "private_only"
    orch.butler_memory.experience.add.assert_not_called()
    provider.sync_turn.assert_not_called()


def test_sync_turn_memory_fails_closed_when_private_filter_errors(monkeypatch):
    monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "1")
    orch = _orch()
    provider = MagicMock()
    orch.memory_provider = provider

    with patch("butler.memory.private_tags.strip_private_tags", side_effect=RuntimeError("boom")):
        result = sync_turn_memory(
            orch,
            "公开问题 <private>secret-q</private>",
            "公开回答 <private>secret-a</private>",
            status=LoopStatus.COMPLETED,
            session_id="wechat:u1",
        )

    assert result["skipped"] is True
    assert result["reason"] == "private_filter_error"
    orch.butler_memory.experience.add.assert_not_called()
    provider.sync_turn.assert_not_called()


def test_sync_turn_memory_provider_failure_keeps_experience_success(monkeypatch):
    monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "1")
    orch = _orch()
    provider = MagicMock()
    provider.sync_turn.side_effect = RuntimeError("provider down")
    orch.memory_provider = provider

    result = sync_turn_memory(orch, "question", "answer", status=LoopStatus.COMPLETED)

    assert result["skipped"] is False
    assert result["experience_updates"] == 1
    assert result["provider_synced"] is False
    assert result["provider_error"] == "provider down"


def test_sync_turn_memory_flushes_observer_queue_on_success(monkeypatch):
    monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "1")
    orch = _orch()
    orch.project_manager.get_current.return_value = SimpleNamespace(workspace="/tmp/demo")

    with patch("butler.memory.observer_queue.flush_observer_queue") as flush_queue:
        result = sync_turn_memory(orch, "question", "answer", status=LoopStatus.COMPLETED)

    assert result["skipped"] is False
    flush_queue.assert_called_once()


def test_clear_session_boundary_memory_removes_tagged_conversation(tmp_path):
    from butler.memory.butler_memory import ButlerMemory

    bm = ButlerMemory(tmp_path)
    bm.experience.add("", "conversation", "Q: 步骤三细节 → A: 完成", tags="session:wechat:u1")
    bm.experience.add("", "experience", "长期偏好", tags="")
    orch = SimpleNamespace(
        butler_memory=bm,
        memory_provider=SimpleNamespace(clear_turn_buffer=lambda: None),
    )

    result = clear_session_boundary_memory(orch, "wechat:u1")

    assert result["removed"] == 1
    assert bm.experience.search("步骤三") == []
    assert bm.experience.search("长期偏好") != []


def test_format_session_end_summary():
    assert "长期记忆 +2" in format_session_end_summary({"memory_updates": 2, "skills_extracted": 0})
    assert "对话过短" in format_session_end_summary({"skipped": True, "reason": "short_history"})


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
    with patch(
        "butler.session.post_session_ops._execute_post_session",
        return_value={"memory_updates": 1, "skills_extracted": 0, "errors": []},
    ) as execute:
        result = trigger_session_end(orch, loop)

    assert result["memory_updates"] == 1
    execute.assert_called_once()


def test_auxiliary_llm_call_factory_is_async():
    from butler.transport.auxiliary_client import auxiliary_llm_call_factory

    fn = auxiliary_llm_call_factory("post_session")
    assert inspect.iscoroutinefunction(fn)


def test_trigger_session_end_awaits_auxiliary_llm_call():
    """Regression: sync factory caused 'object str can't be used in await'."""
    orch = _orch()
    filler = "x" * 80
    loop = SimpleNamespace(
        messages=[
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
            {"role": "user", "content": filler},
        ]
    )

    with patch(
        "butler.transport.auxiliary_client.auxiliary_complete",
        return_value='{"updates": []}',
    ):
        result = trigger_session_end(orch, loop)

    assert result.get("skipped") is not True
    assert result.get("errors", []) == []
