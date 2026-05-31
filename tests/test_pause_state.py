"""Tests for butler.workflows.pause_state."""

from __future__ import annotations

from butler.workflows.pause_state import (
    WorkflowPauseState,
    clear_workflow_pause,
    load_workflow_pause,
    save_workflow_pause,
)


def _sample_state(session_key: str = "sess-1") -> WorkflowPauseState:
    return WorkflowPauseState(
        workflow="deploy",
        step_id="step-2",
        session_key=session_key,
        execution_order=["step-1", "step-2", "step-3"],
        completed_steps=["step-1"],
        created_at=1717000000.5,
    )


class TestWorkflowPauseState:
    def test_to_dict_serializes_correctly(self):
        state = _sample_state()
        assert state.to_dict() == {
            "workflow": "deploy",
            "step_id": "step-2",
            "session_key": "sess-1",
            "execution_order": ["step-1", "step-2", "step-3"],
            "completed_steps": ["step-1"],
            "created_at": 1717000000.5,
        }


class TestSaveLoadWorkflowPause:
    def test_save_then_load(self, tmp_path):
        state = _sample_state()
        save_workflow_pause(state, workspace=tmp_path)

        loaded = load_workflow_pause("sess-1", workspace=tmp_path)
        assert loaded == state

    def test_load_missing_file_returns_none(self, tmp_path):
        assert load_workflow_pause("missing", workspace=tmp_path) is None

    def test_load_invalid_json_returns_none(self, tmp_path):
        save_workflow_pause(_sample_state(), workspace=tmp_path)
        pause_file = tmp_path / ".butler" / "workflow_pause.json"
        pause_file.write_text("not json", encoding="utf-8")

        assert load_workflow_pause("sess-1", workspace=tmp_path) is None


class TestClearWorkflowPause:
    def test_clear_then_load_returns_none(self, tmp_path):
        state = _sample_state()
        save_workflow_pause(state, workspace=tmp_path)
        assert load_workflow_pause("sess-1", workspace=tmp_path) is not None

        clear_workflow_pause("sess-1", workspace=tmp_path)
        assert load_workflow_pause("sess-1", workspace=tmp_path) is None
