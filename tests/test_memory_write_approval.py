"""Tests for owner memory write approval."""

import json

import pytest

from butler.memory.owner_write_pending import (
    approve_all_owner_pending,
    approve_owner_pending,
    list_owner_pending,
    memory_write_approval_mode,
    queue_owner_write,
    reject_owner_pending,
    scope_requires_write_approval,
)


@pytest.mark.unit
def test_scope_requires_owner_scopes(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_WRITE_APPROVAL", "owner_scopes")
    assert scope_requires_write_approval("owner_profile") is True
    assert scope_requires_write_approval("owner_experience") is True
    assert scope_requires_write_approval("project_notes", "append") is False


@pytest.mark.unit
def test_scope_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_WRITE_APPROVAL", "0")
    assert scope_requires_write_approval("owner_profile") is False


@pytest.mark.unit
def test_queue_and_approve(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()

    class FakeProfile:
        def add(self, content):
            self.last = content
            return {"success": True}

        def sync(self):
            pass

    class FakeBM:
        def __init__(self):
            self.profile = FakeProfile()

        def sync_profile_vectors(self):
            pass

        def add_experience(self, **kwargs):
            return 1

    item = queue_owner_write(scope="owner_profile", content="prefers concise replies")
    assert item["id"]
    assert len(list_owner_pending()) == 1

    from butler.memory.facade import ButlerMemoryService

    provider = ButlerMemoryService()
    provider._butler_global = FakeBM()  # noqa: SLF001 — test stub
    monkeypatch.setenv("BUTLER_MEMORY_WRITE_APPROVAL", "owner_scopes")
    result = json.loads(
        provider._remember(
            {
                "scope": "owner_profile",
                "content": "another",
            }
        )
    )
    assert result.get("classification") == "pending"

    bm = FakeBM()
    approved = approve_owner_pending(0, bm)
    assert approved.get("ok") is True
    assert len(list_owner_pending()) == 1
    assert approve_all_owner_pending(bm) == 1
    assert list_owner_pending() == []


@pytest.mark.unit
def test_reject_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    queue_owner_write(scope="owner_experience", content="note")
    assert reject_owner_pending(0) is True
    assert list_owner_pending() == []
