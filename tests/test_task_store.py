"""Tests for delegate task persistence."""

from butler.runtime.task_store import complete_task, create_task, get_task, list_recent_tasks


def test_task_store_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    rec = create_task(session_key="s1", role="dev", task_preview="fix bug")
    task_id = rec["task_id"]
    assert get_task(task_id)["status"] == "running"
    complete_task(task_id, success=True, report_headline="ok", summary="done")
    done = get_task(task_id)
    assert done["status"] == "completed"
    assert done["success"] is True
    recent = list_recent_tasks("s1", limit=3)
    assert recent and recent[0]["task_id"] == task_id
